import os
from typing import Optional


class EnvLoader:
    @staticmethod
    def get_env_or_die(env_key: str, default: Optional[str] = None) -> str:
        env_value = os.environ.get(env_key, default=default)
        if env_value is None or env_value == "":
            raise ValueError(f"Env variable {env_key} is required")
        return env_value
