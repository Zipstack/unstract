import logging
import signal

from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.tool.executor import ToolExecutor
from unstract.sdk1.tool.parser import ToolArgsParser

logger = logging.getLogger(__name__)


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
        # Ignore SIGTERM and SIGINT from the very beginning to prevent
        # any interruption of tool operations
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        logger.info(
            "Tool configured to ignore SIGTERM/SIGINT for uninterrupted execution"
        )

        parsed_args = ToolArgsParser.parse_args(args)
        executor = ToolExecutor(tool=tool)
        executor.execute(parsed_args)
