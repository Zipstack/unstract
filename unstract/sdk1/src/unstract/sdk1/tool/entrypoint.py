from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.executor import ToolExecutor
from unstract.sdk.tool.parser import ToolArgsParser


class ToolEntrypoint:
    """Class that contains methods for the entrypoint for a tool."""

    @staticmethod
    def launch(tool: BaseTool, args: list[str]) -> None:
        """Entrypoint function for a tool.

        It parses the arguments passed to a tool and executes
        the intended command.

        Args:
            tool (AbstractTool): Tool to execute
            args (List[str]): Arguments passed to a tool
        """
        parsed_args = ToolArgsParser.parse_args(args)
        executor = ToolExecutor(tool=tool)
        executor.execute(parsed_args)
