from pydantic import BaseModel, Field
from tools.base import Tool, ToolKind, ToolInvocation, ToolResult
from utils.paths import resolve_path, is_binary_file
from utils.text import count_tokens, truncate_text


class ReadFileParams(BaseModel):
    path: str = Field(
        ...,
        description="Path to the file to read ( relative to working dir or absoulute path)",
    )
    offset: int = Field(1, ge=1, description="Line number to start reading from")
    limit: int | None = Field(
        None,
        ge=1,
        description="Number of lines to read ( if None, read till end of file)",
    )


class ReadFileTool(Tool):
    name: str = "read_file"
    description = (
        "Read the contents of a text file. Returns the file content with line numbers. "
        "For large files, use offset and limit to read specific portions. "
        "Cannot read binary files (images, executables, etc.)."
    )
    kind: ToolKind = ToolKind.READ
    schema = ReadFileParams
    MAX_FILE_SIZE = 10 * 1024 * 1024
    MAX_OUTPUT_TOKENS = 25000

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ReadFileParams(**invocation.params)
        path = resolve_path(invocation.cwd, params.path)
        if not path.exists():
            return ToolResult.error_result(f"File not found: {path}")
        if not path.is_file():
            return ToolResult.error_result(f"Path is not a file: {path}")

        file_size = path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            return ToolResult.error_result(
                f"File is too large: {file_size/1024/1024 : .1f} MB"
                f"Limit is {self.MAX_FILE_SIZE/1024/1024 : .1f} MB"
            )
        if is_binary_file(path):
            file_size_mb = file_size / 1024 / 1024
            size_str = (
                f"{file_size_mb : .2f} MB"
                if file_size_mb >= 1
                else f"{file_size : .1f} KB"
            )
            return ToolResult.error_result(
                f"Cannot read binary files: {path.name} ({size_str})"
                f"This tool only reads text file"
            )
        try:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="latin-1")

            lines = content.splitlines()
            total_lines = len(lines)

            if total_lines == 0:
                return ToolResult.success_result(
                    "File is empty", metadata={"total_lines": 0}
                )

            start_index = max(0, params.offset - 1)
            end_index = (
                start_index + params.limit if params.limit is not None else total_lines
            )

            if start_index >= total_lines:
                return ToolResult.success_result(
                    f"Offset {params.offset} is beyond the end of the file"
                    f"File has {total_lines} lines"
                )

            selected_lines = lines[start_index:end_index]
            formated_line = []

            for i, line in enumerate(selected_lines, start=start_index + 1):
                formated_line.append(f"{i:6} | {line}")

            output = "\n".join(formated_line)
            token_count = count_tokens(output, "gpt-4o-mini")
            truncated = False
            if token_count > self.MAX_OUTPUT_TOKENS:
                output = truncate_text(
                    output,
                    self.MAX_OUTPUT_TOKENS,
                    suffix=f"\n...[TRUNCATED {total_lines} lines]",
                )
                truncated = True
            metadata_lines = []

            if start_index > 0 or end_index < total_lines:
                metadata_lines.append(
                    f"Showing lines {start_index + 1} - {end_index} of {total_lines}"
                )

            if metadata_lines:
                header = " | ".join(metadata_lines) + "\n\n"
                output = header + output

            result_lines = min(len(selected_lines), params.limit or total_lines)

            return ToolResult.success_result(
                output=output,
                truncated=truncated,
                metadata={
                    "path": str(path),
                    "total_lines": total_lines,
                    "show_start": start_index + 1,
                    "show_end": end_index,
                },
            )

        except Exception as e:
            return ToolResult.error_result(f"Error reading file: {str(e)}")
