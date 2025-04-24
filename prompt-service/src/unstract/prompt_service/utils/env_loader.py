import os


def get_env_or_die(env_key: str, default: str | None = None) -> str:
    """Get the value of an environment variable or raise an error if it is not set.

    Args:
        env_key (str): Name of the environment variable.
        default (Optional[str]): Default value if the variable is not set.

    Returns:
        str: The value of the environment variable.

    Raises:
        ValueError: If the variable is not set.
    """
    env_value = os.environ.get(env_key, default=default)
    if env_value is None:
        raise ValueError(f"Env variable {env_key} is required")
    return env_value
