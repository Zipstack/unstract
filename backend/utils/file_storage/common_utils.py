import os


class FileStorageUtil:
    @staticmethod
    def get_env_or_die(env_key: str) -> str:
        """Returns the value of an env variable.
        If its empty or None, raises an error and exits
        Args:
            env_key (str): Key to retrieve
        Returns:
            str: Value of the env
        """
        env_value = os.environ.get(env_key)
        if env_value is None or env_value == "":
            raise ValueError(f"Env variable '{env_key}' is required")
        return env_value
