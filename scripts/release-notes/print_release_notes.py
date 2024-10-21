# type: ignore
import argparse
import json
import re
import sys
from pathlib import Path

from packaging import version

# Sample JSON data (in a separate file 'warnings.json')
# {
#   "v0.93.0": {
#     "message": "This a WARNING note",
#     "warning": true
#   },
#   "v0.95.0": {
#     "message": "This is an INFO note",
#     "warning": false
#   }
# }

RELEASE_NOTES_FILE_PATH = Path(__file__).with_name("release_notes.json").absolute()


class Colour:
    BLUE = "\033[94m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    DEFAULT = "\033[39m"
    YELLOW = "\033[33m"


def colour(text, colour: Colour):
    return f"{colour}{text}{Colour.DEFAULT}"


def load_release_notes(json_file):
    """Load warnings from a JSON file."""
    with open(json_file) as file:
        return json.load(file)


def is_valid_semver(ver):
    """Check if a version string follows semantic versioning (vX.X.X)."""
    semver_pattern = r"^v\d+\.\d+\.\d+(-[a-zA-Z0-9]+(\.\d+)?)?$"
    return re.match(semver_pattern, ver) is not None


def print_release_notes(current_version, target_version, release_notes):
    """Print relevant warnings if current_version < warning_version <=
    target_version."""
    messages_to_print = []
    for note_version, release_note in release_notes.items():
        if (
            version.parse(current_version)
            < version.parse(note_version)
            <= version.parse(target_version)
        ):
            # Check release note and display warning in yellow release_note
            message = (
                f"{colour('WARNING', Colour.YELLOW)}: "
                if release_note["warning"]
                else ""
            )
            message += (
                f"[from {colour(note_version, Colour.BLUE)}] "
                f"{release_note['message']}\n"
            )
            messages_to_print.append(message)

    if not messages_to_print:
        return

    print("\n########################## RELEASE NOTES ##########################")
    for message in messages_to_print:
        print(message)
    print("###################################################################\n")


def main():
    """Main function to load warnings and check versions."""
    parser = argparse.ArgumentParser(
        description="Check for version upgrade warnings based on semantic versioning."
    )
    parser.add_argument(
        "current_version",
        type=str,
        help="Current version of Unstract (e.g., v0.85.0)",
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
    release_notes = load_release_notes(RELEASE_NOTES_FILE_PATH)

    # Validate the current_version and target_version
    if not is_valid_semver(current_version) or not is_valid_semver(target_version):
        print(
            f"\n{colour('WARNING', Colour.YELLOW)}: You are trying to update between "
            f"versions\n\t({colour(current_version, Colour.BLUE)} -> "
            f"{colour(target_version, Colour.BLUE)})\nPlease check for applicable "
            f"warnings in '{colour(RELEASE_NOTES_FILE_PATH, Colour.BLUE)}'\n"
        )
        sys.exit(1)

    print_release_notes(current_version, target_version, release_notes)


if __name__ == "__main__":
    main()
