# type: ignore
import argparse
import json
import re
import sys
from pathlib import Path

from packaging import version

# Sample JSON data (in a separate file 'warnings.json')
# {
#   "v0.91.5": "Warning message for version v0.91.5",
#   "v1.2.0": "Warning message for version v1.2.0"
# }

WARNINGS_FILE_PATH = Path(__file__).with_name("warnings.json").absolute()


class Colour:
    BLUE = "\033[94m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    DEFAULT = "\033[39m"
    YELLOW = "\033[33m"


def colour(text, colour: Colour):
    return f"{colour}{text}{Colour.DEFAULT}"


def load_warnings(json_file):
    """Load warnings from a JSON file."""
    with open(json_file) as file:
        return json.load(file)


def is_valid_semver(ver):
    """Check if a version string follows semantic versioning (vX.X.X)."""
    semver_pattern = r"^v\d+\.\d+\.\d+(-[a-zA-Z0-9]+(\.\d+)?)?$"
    return re.match(semver_pattern, ver) is not None


def print_warnings(current_version, target_version, warnings):
    """Print relevant warnings if current_version < warning_version <=
    target_version."""
    print("\n######################## RELEASE WARNINGS ########################")
    for warning_version, warning_message in warnings.items():
        if (
            version.parse(current_version)
            < version.parse(warning_version)
            <= version.parse(target_version)
        ):
            print(
                f"{colour('WARNING', Colour.YELLOW)}: [from "
                f"{colour(warning_version, Colour.BLUE)}] {warning_message}"
            )
    print("###################################################################")


def main():
    """Main function to load warnings and check versions."""
    parser = argparse.ArgumentParser(
        description="Check for version upgrade warnings based on semantic versioning."
    )
    parser.add_argument(
        "current_version",
        type=str,
        help="Current version of the software (e.g., v0.85.0)",
    )
    parser.add_argument(
        "target_version",
        type=str,
        help="Target version for the upgrade (e.g., v0.90.0)",
    )

    args = parser.parse_args()

    current_version = args.current_version
    target_version = args.target_version

    # Load the warnings from the JSON file
    warnings = load_warnings(WARNINGS_FILE_PATH)

    # Validate the current_version and target_version
    if not is_valid_semver(current_version) or not is_valid_semver(target_version):
        print(
            f"{colour('WARNING', Colour.YELLOW)}: You are trying to update between "
            f"versions\n\t({colour(current_version, Colour.BLUE)} -> "
            f"{colour(target_version, Colour.BLUE)})\nPlease check for applicable "
            f"warnings in '{colour(WARNINGS_FILE_PATH, Colour.BLUE)}'"
        )
        sys.exit(1)

    # Print relevant warnings
    print_warnings(current_version, target_version, warnings)


if __name__ == "__main__":
    main()
