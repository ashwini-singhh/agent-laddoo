from pathlib import Path
from tools.base import Tool, ToolResult, ToolInvocation
import logging
from typing import Any
from tools.builtin import get_all_builtin_tools

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool {tool.name} is already registered. Overwriting.")

        self._tools[tool.name] = tool
        logger.debug(f"Tool {tool.name} registered successfully")

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Tool {name} unregistered successfully")
            return True
        logger.warning(f"Tool {name} not found")
        return False

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_all_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        for tool in self._tools.values():
            tools.append(tool)
        return tools

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self.get_all_tools()]

    async def invoke(self, name: str, params: dict[str, Any], cwd: Path) -> ToolResult:
        tool = self.get_tool(name)
        if not tool:
            return ToolResult.error_result(
                f"Tool {name} not found",
                metadata={
                    "tool_name": name,
                },
            )

        errors = tool.validate_params(params)
        if errors:
            return ToolResult.error_result(
                f"Validation errors: {'; '.join(errors)}",
                metadata={
                    "tool_name": name,
                    "errors": errors,
                },
            )

        invocation = ToolInvocation(params=params, cwd=cwd)
        try:
            result = await tool.execute(invocation)
        except Exception as e:
            logger.error(f"Error executing tool {name} raised unexpected result")
            result = ToolResult.error_result(
                f"Error executing tool: {str(e)}",
                metadata={
                    "tool_name": name,
                },
            )
        return result

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __getitem__(self, name: str) -> Tool:
        return self._tools[name]

    def __iter__(self):
        return iter(self._tools.values())

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={list(self._tools.keys())})"


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool_class in get_all_builtin_tools():
        registry.register(tool_class())
    return registry
