import os
import asyncio
from openai import AsyncOpenAI, RateLimitError, APIConnectionError, AuthenticationError
from typing import Any, AsyncGenerator
from .response import StreamEvent, TokenUsage, StreamEventType, TextDelta, ToolCall , ToolCallDelta , parse_tool_call_arguments
from config.config import Config

class LLMClient:
    def __init__(self, config : Config ) -> None:
        self.client: AsyncOpenAI | None = None
        self.max_retries: int = 3
        self.config = config

    def get_client(self) -> AsyncOpenAI:
        """Ensure Singularity.
        Returns the client if it is already initialized
        Otherwise, initializes the client and returns it
        """
        if self.client is None:
            self.client = AsyncOpenAI(
                api_key= self.config.api_key,   #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
                base_url= self.config.base_url,  #"https://openrouter.ai/api/v1"
            )
        return self.client

    async def close(self) -> None:
        if self.client is None:
            return
        await self.client.close()
        self.client = None

    def _build_tools(self, tools: list[dict[str, Any]]):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        stream: bool = True,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:

        client = self.get_client()
        kwargs = {
            "model" : self.config.model.name,
            "messages": messages,
            "stream": stream,
        }
       
        if tools:
            kwargs["tools"] = self._build_tools(tools)
            kwargs["tool_choice"] = "auto"

        for attempt in range(self.max_retries + 1):
            try:
                if stream:
                    async for event in self._stream_response(client, kwargs):
                        yield event
                else:
                    event = await self._non_stream_response(client, kwargs)
                    yield event
                return  # Success, break the retry loop

            except AuthenticationError as e:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=f"Authentication error: {e}. Please check your API key.",
                )
                return
            except RateLimitError as e:
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=f"Rate limit exceeded: {e}",
                    )
                    return
            except APIConnectionError as e:
                if attempt < self.max_retries:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                else:
                    yield StreamEvent(
                        type=StreamEventType.ERROR,
                        error=str(f"connection error {e}"),
                    )
                    return
            except Exception as e:
                yield StreamEvent(
                    type=StreamEventType.ERROR,
                    error=str(e),
                )
                return

        return

    async def _stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> AsyncGenerator[StreamEvent, None]:
       
        response = await client.chat.completions.create(**kwargs)

        usage: TokenUsage | None = None
        finish_reason: str | None = None
        tool_calls: dict[ int , dict[ str , Any]] = {}

        async for chunk in response:
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    total_tokens=chunk.usage.total_tokens,
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    cached_tokens=(
                        getattr(chunk.usage.prompt_tokens_details, "cached_tokens", 0)
                        if hasattr(chunk.usage, "prompt_tokens_details")
                        else 0
                    ),
                )
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    text_delta=TextDelta(content=delta.content),
                )
            
            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    idx = tool_call_delta.index

                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            'id' : tool_call_delta.id or "",
                            'name' : '',
                            'arguments': ''
                        }

                    if tool_call_delta.function:
                        if tool_call_delta.function.name:
                            tool_calls[idx]['name'] = tool_call_delta.function.name
                            yield StreamEvent(
                                type = StreamEventType.TOOL_CALL_START,
                                tool_call_delta = ToolCallDelta(
                                    call_id = tool_call_delta.id or "",
                                    name = tool_call_delta.function.name
                                )
                            )
                        if tool_call_delta.function.arguments:
                            tool_calls[idx]['arguments'] += tool_call_delta.function.arguments
                            yield StreamEvent(
                                type = StreamEventType.TOOL_CALL_DELTA,
                                tool_call_delta = ToolCallDelta(
                                    call_id = tool_call_delta.id or "",
                                    name = tool_call_delta.function.name,
                                    arguments_delta = tool_call_delta.function.arguments
                                )
                            )
                    
        for idx, tool_call in tool_calls.items():
            yield StreamEvent(
                type = StreamEventType.TOOL_CALL_COMPLETE,
                tool_call = ToolCall(
                    call_id = tool_call['id'],
                    name = tool_call['name'],
                    arguments = parse_tool_call_arguments(tool_call['arguments'])
                )
            )
            
        yield StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def _non_stream_response(
        self, client: AsyncOpenAI, kwargs: dict[str, Any]
    ) -> StreamEvent:
        response = await client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        text_delta = None
        if message.content:
            text_delta = TextDelta(content=message.content)
        
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCall(
                    call_id = tc.id,
                    name = tc.function.name,
                    arguments= parse_tool_call_arguments( tc.function.arguments)
                ))
        token_usage = None
        if response.usage:
            token_usage = TokenUsage(
                total_tokens=response.usage.total_tokens,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                cached_tokens=(
                    getattr(response.usage.prompt_tokens_details, "cached_tokens", 0)
                    if hasattr(response.usage, "prompt_tokens_details")
                    else 0
                ),
            )

        return StreamEvent(
            type=StreamEventType.MESSAGE_COMPLETE,
            text_delta=text_delta,
            usage=token_usage,
            finish_reason=choice.finish_reason,
        )
