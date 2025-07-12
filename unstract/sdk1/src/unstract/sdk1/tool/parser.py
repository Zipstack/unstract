import argparse

from dotenv import find_dotenv, load_dotenv
from unstract.sdk.constants import LogLevel


class ToolArgsParser:
    """Class to help with parsing arguments to a tool."""

    @staticmethod
    def parse_args(args_to_parse: list[str]) -> argparse.Namespace:
        """Helps parse arguments to a tool.

        Args:
            args_to_parse (List[str]): Command line arguments received by a tool

        Returns:
            argparse.Namespace: Parsed arguments
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--command", type=str, help="Command to execute", required=True
        )
        parser.add_argument(
            "--settings", type=str, help="Settings to be used", required=False
        )
        parser.add_argument(
            "--log-level",
            type=LogLevel,
            help="Log level",
            required=False,
            default=LogLevel.ERROR,
        )
        parser.add_argument(
            "--env",
            type=str,
            help="Env file to load environment from",
            required=False,
            default=find_dotenv(usecwd=True),
        )
        parsed_args = parser.parse_args(args_to_parse)
        ToolArgsParser.load_environment(parsed_args.env)
        return parsed_args

    @staticmethod
    def load_environment(path: str | None = None) -> None:
        """Loads env variables with python-dotenv.

        Args:
            path (Optional[str], optional): Path to the env file to load.
                Defaults to None.
        """
        if path is None:
            load_dotenv()
        else:
            load_dotenv(path)
