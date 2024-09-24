import logging
import os
import sys

from unstract.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def main() -> None:
    """Initiating and running tools."""
    registry = ToolRegistry()
    registry.load_all_tools_to_disk()


if __name__ == "__main__":
    """Pull and Load all private tools
    Steps:
    1. Load from registry.yaml
    2. Pull the images
    3. Load tool data in to json file
    """
    RUNNER_HOST = "UNSTRACT_RUNNER_HOST"
    RUNNER_PORT = "UNSTRACT_RUNNER_PORT"
    if RUNNER_HOST not in os.environ or RUNNER_PORT not in os.environ:
        print(
            "Mandatory environment variables UNSTRACT_RUNNER_HOST "
            "and UNSTRACT_RUNNER_PORT are missing."
        )
        print(
            f"Usage: {RUNNER_HOST}=<host> {RUNNER_PORT}=<port> "
            "python load_tools_to_json.py"
        )
        sys.exit(1)
    main()
