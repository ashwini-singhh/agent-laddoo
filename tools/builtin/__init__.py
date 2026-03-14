from tools.builtin.read_file import ReadFileTool
from tools.builtin.write_file import WriteFileTool
from tools.builtin.edit_file import EditFileTool

__all__ = ["ReadFileTool", "WriteFileTool", "EditFileTool"]


def get_all_builtin_tools() -> list[type]:
    return [ReadFileTool, WriteFileTool, EditFileTool]
