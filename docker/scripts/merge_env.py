#
# Usage:
#   python merge_env.py [--dry-run] base_env_path target_env_path
#
# e.g.
# Dry run:
#   python merge_env.py --dry-run sample.env .env
# Actual run:
#   python merge_env.py sample.env .env
#
import sys

PREFERRED_BASE_ENV_KEYS = [
    "STRUCTURE_TOOL_IMAGE_URL",
    "STRUCTURE_TOOL_IMAGE_TAG",
    "CONTAINER_CLIENT_PATH",
]
DEFAULT_AUTH_KEY = "unstract"
DEFAULT_ADMIN_KEY = "admin"
SET_DEFAULT_KEYS = {
    "DEFAULT_AUTH_USERNAME": DEFAULT_AUTH_KEY,
    "DEFAULT_AUTH_PASSWORD": DEFAULT_AUTH_KEY,
    "SYSTEM_ADMIN_USERNAME": DEFAULT_ADMIN_KEY,
    "SYSTEM_ADMIN_PASSWORD": DEFAULT_ADMIN_KEY,
}


def _extract_kv_from_line(line: str) -> tuple[str, str]:
    parts = line.split("=", 1)
    if len(parts) != 2:
        raise ValueError(f"{line}")
    key, value = parts
    key = key.strip()
    value = value.strip()
    return key, value


def _extract_from_env_file(file_path: str) -> dict[str, str]:
    env = {}

    with open(file_path) as file:
        for line in file:
            if not line.strip() or line.startswith("#"):
                continue

            key, value = _extract_kv_from_line(line)

            env[key.strip()] = value.strip()

    return env


def _merge_to_env_file(base_env_file_path: str, target_env: dict[str, str] = {}) -> str:
    """Generates file contents after merging input base env file path with
    target env.

    Args:
        base_env_file_path (string): Base env file path e.g. `sample.env`
        target_env (dict, optional): Target env to use for merge e.g. `.env`

    Returns:
        string: File contents after merge.
    """
    merged_contents = []

    with open(base_env_file_path) as file:
        for line in file:
            # Preserve location of empty lines and comments
            # for easy diff.
            if not line.strip() or line.startswith("#"):
                merged_contents.append(line)
                continue

            key, value = _extract_kv_from_line(line)

            # Preserve following keys at base env file path:
            # - preferred keys
            # - newly added keys
            # Everything else, take existing configured values
            # from target env.
            if key not in PREFERRED_BASE_ENV_KEYS and key in target_env:
                value = target_env.get(key, value)

            # Set default value for these keys always.
            if not value and key in SET_DEFAULT_KEYS:
                value = SET_DEFAULT_KEYS[key]

            merged_contents.append(f"{key}={value}\n")

    # Allow extras from target_env which is not present in base_env
    base_env = _extract_from_env_file(base_env_file_path)
    additional_env_header_added = False

    for key in target_env:
        if key not in base_env:
            if not additional_env_header_added:
                additional_env_header_added = True
                merged_contents.append("\n\n# Additional envs\n")
            merged_contents.append(f"{key}={target_env.get(key)}\n")

    return "".join(merged_contents)


def _save_merged_contents(
    file_path: str, file_contents: str, dry_run: bool = False
) -> None:
    if dry_run:
        print(f"===== merged:{file_path} =====")
        print(file_contents)
        print("-----------")
    else:
        with open(file_path, "w") as file:
            file.write(file_contents)


def merge_env(
    base_env_file_path: str, target_env_file_path: str, dry_run: bool = False
) -> None:
    target_env = _extract_from_env_file(target_env_file_path)
    merged_contents = _merge_to_env_file(base_env_file_path, target_env=target_env)
    _save_merged_contents(target_env_file_path, merged_contents, dry_run=dry_run)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4:
            dry_run = True if sys.argv[1] == "--dry-run" else False
            merge_env(sys.argv[2], sys.argv[3], dry_run=dry_run)
        else:
            merge_env(sys.argv[1], sys.argv[2])
    except IndexError:
        print(f"Invalid env paths for merge: {sys.argv}")
        sys.exit(1)
    except ValueError as e:
        print(f"Malformed env config: {str(e)}")
        sys.exit(1)
