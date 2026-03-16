from __future__ import annotations
from typing import AsyncGenerator
from agent.agent_event import AgentEvent, AgentEventType
from client.response import StreamEventType, ToolResultMessage
import json
from config.config import Config
from agent.session import Session

class Agent:
    def __init__(self, config: Config):
        self.config = config
        self.session: Session | None = Session(config)

    async def run(self, message: str):  
        yield AgentEvent.agent_start(message=message)
        self.session.context_manager.add_user_message(message)
        final_response: str | None = None
        async for event in self._agentic_loop(message):
            yield event

            if event.type == AgentEventType.AGENT_ERROR:
                break
            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")

        yield AgentEvent.agent_end(response=final_response)

    async def _agentic_loop(self, message: str) -> AsyncGenerator[AgentEvent]:
        max_turns = self.config.max_turns
        tool_schemas = self.session.tool_registry.get_schemas()

        for turn in range(max_turns):
            self.session.increment_turn()
            response_text = ""
            tool_calls: list[ToolCall] = []
            
            async for event in self.session.client.chat_completion(
                messages=self.session.context_manager.get_messages(),
                tools=tool_schemas if tool_schemas else None,
                stream=True,
            ):
                if event.type == StreamEventType.TEXT_DELTA:
                    if event.text_delta:
                        content = event.text_delta.content
                        response_text += content
                        yield AgentEvent.text_delta(content=content)
                elif event.type == StreamEventType.ERROR:
                    yield AgentEvent.agent_error(error=event.error or "Unknown error")
                elif event.type == StreamEventType.TOOL_CALL_COMPLETE:
                    if event.tool_call:
                        tool_calls.append(event.tool_call)


            self.session.context_manager.add_assistant_message(response_text or None,
                ([
                    {
                        'id': tc.call_id,
                        'type':'function',
                        'function':{
                            'name': tc.name,
                            'arguments': json.dumps(tc.arguments),
                        }
                    }
                    for tc in tool_calls 
                ]
                if tool_calls else None),
            )
            if response_text:
                yield AgentEvent.text_complete(content=response_text)
            
            if not tool_calls:
                return 
            
            tool_call_results: list[ToolResultMessage] = []

            for tool_call in tool_calls:
                yield AgentEvent.tool_call_start(
                    call_id=tool_call.call_id,
                    name=tool_call.name,
                    arguments=tool_call.arguments,
                )
                result = await self.session.tool_registry.invoke(tool_call.name, tool_call.arguments, self.config.cwd)
                
                yield AgentEvent.tool_call_complete(
                    call_id=tool_call.call_id,
                    name=tool_call.name,
                    result=result,
                )

                tool_call_results.append(
                    ToolResultMessage(
                        tool_call_id=tool_call.call_id,
                        content=result.to_model_output(),
                        is_error= not result.success,
                    )
                )
            
            for tool_result in tool_call_results:
                self.session.context_manager.add_tool_result(tool_result.tool_call_id, tool_result.content)

        yield AgentEvent.agent_error(f"Maximum turns({self.config.max_turns}) exceeded")
    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.session and self.session.client:
            await self.session.client.close()
            self.session = None



