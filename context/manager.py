from prompts.system import get_system_prompt
from dataclasses import dataclass, field
from utils.text import count_tokens
from typing import Any
from config.config import Config

@dataclass
class MessageItem:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}
        
        # Assistant and Tool messages REQUIRE content field for many providers (e.g. StepFun)
        if self.role == "assistant":
            result["content"] = self.content if self.content else ""
        elif self.role == "tool":
            result["content"] = self.content if self.content else ""
        elif self.content:
            result["content"] = self.content

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        return result



class ContextManager:
    def __init__(self, config: Config):
        self.config = config
        self._system_prompt = get_system_prompt(config)
        self._messages: list[MessageItem] = []
        self.model_name = self.config.model.name

    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role="user",
            content=content,
            token_count=count_tokens(content, self.model_name),
        )
        self._messages.append(item)

    def add_assistant_message(self, content: str, tool_calls: list[dict[str , Any]] | None) -> None:
        item = MessageItem(
            role="assistant",
            content=content or "",
            token_count=count_tokens(content or "", self.model_name),
            tool_calls=tool_calls or [],    
        )
        self._messages.append(item)

    def add_tool_result(self,tool_call_id : str ,content: str) -> None:
        item = MessageItem(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            token_count=count_tokens(content or "", self.model_name),
        )
        self._messages.append(item)

    def add_system_prompt(self, content: str) -> None:
        item = MessageItem(
            role="system",
            content=content,
            token_count=count_tokens(content or "", self.model_name),
        )
        self._messages.append(item)

    def get_messages(self) -> list[dict[str, Any]]:
        message = []
        if self._system_prompt:
            message.append({"role": "system", "content": self._system_prompt})

        for item in self._messages:
            message.append(item.to_dict())

        return message

    def get_token_count(self) -> int:
        return sum(item.token_count for item in self._messages)
