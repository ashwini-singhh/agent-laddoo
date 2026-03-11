import asyncio
import click
from typing import Any
from agent.agent import Agent
from agent.agent_event import AgentEventType
from ui.tui import TUI, get_console
from pathlib import Path
from config.loader import load_config
from utils.errors import ConfigError
from config.config import Config
import sys
console = get_console()


class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.tui = TUI(config , console)
        self.config = config

    def _get_tool_kind(self, tool_name: str) -> str | None:
        tool_kind = None
        tool = self.agent.session.tool_registry.get_tool(tool_name)
        if not tool:
            tool_kind = None

        tool_kind = tool.kind.value

        return tool_kind

    async def run_single(self, message: str) -> str | None:
        async with Agent(config=self.config) as agent:
            self.agent = agent
            return await self._process_message(message)

    async def run_interactive(self) -> None:

        self.tui.print_welcome(
            'AI Agent',
            lines = [
                f'model : {self.config.model.name}',
                f'cwd: {self.config.cwd}',
                "commands: /help /config /approval /model /exit",
                'Type your message and press Enter to send it to the agent.',
            ],
        )

        async with Agent(config=self.config) as agent:
            self.agent = agent
            while True:
                try:
                    message = console.input("\n[user]>[/user]").strip()
                    if not message:
                        continue
                    if message == "/exit":
                        break
                    await self._process_message(message)
                except KeyboardInterrupt:
                    console.print("\n[dim]Use /exit to quit[/dim]")
                except EOFError:
                    break
        
        console.print("\n[dim]Good bye...[/dim]")

                

    async def _process_message(self, message: str) -> str | None:
        if not self.agent:
            raise RuntimeError("Agent not initialized")
        final_response: str | None = None

        assitance_streaming = False

        async for event in self.agent.run(message):
            # print(event )
            if event.type == AgentEventType.TEXT_DELTA:
                if not assitance_streaming:
                    self.tui.begin_assistant()
                    assitance_streaming = True
                self.tui.stream_assistant_delta(event.data["content"])

            elif event.type == AgentEventType.TEXT_COMPLETE:
                final_response = event.data.get("content")
                if assitance_streaming:
                    self.tui.end_assistant()
                    assitance_streaming = False
            elif event.type in (AgentEventType.AGENT_START, AgentEventType.AGENT_END):
                continue
            
            elif event.type == AgentEventType.TOOL_CALL_START:
                tool_name = event.data.get("name", "UNKNOWN")
                tool = self.agent.session.tool_registry.get_tool(tool_name)
                tool_kind = tool.kind.value if tool else None
                
                self.tui.tool_call_start(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("arguments", {}),
                )

            elif event.type == AgentEventType.TOOL_CALL_COMPLETE:
                tool_name = event.data.get("name", "unknown")
                tool_kind = self._get_tool_kind(tool_name)
                self.tui.tool_call_complete(
                    event.data.get("call_id", ""),
                    tool_name,
                    tool_kind,
                    event.data.get("success", False),
                    event.data.get("output", ""),
                    event.data.get("error"),
                    event.data.get("metadata"),
                    event.data.get("diff"),
                    event.data.get("truncated", False),
                    event.data.get("exit_code"),
                )
            elif event.type == AgentEventType.AGENT_ERROR:
                error = event.data.get("error", "Unknown error")
                console.print(f"\n[error]Error: {error}[/error]")
            
        return final_response


@click.command()
@click.argument("prompt", required=False)
@click.option(
    '--cwd',
    '-c',
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    default=Path.cwd(),
    help='Working directory'
)
def main(prompt: str | None,
    cwd: Path | None
):

    
    try:
        config = load_config(cwd = cwd)
    except ConfigError as e:
        console.print(f"[error]Configuration Error: {e}[/error]")

    errors = config.validate()
    if errors:
        console.print(f"[error]Configuration Error: {errors}[/error]")
        sys.exit(1)

    cli = CLI(config)
    # messages = [{
    #     'role': 'user',
    #     'content': prompt
    # }]
    if prompt:
        result = asyncio.run(cli.run_single(prompt))
        if result is None:
            exit(1)
    else:
        
        asyncio.run(cli.run_interactive())


if __name__ == "__main__":
    main()
