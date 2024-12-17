import json
import os
from typing import Any, Optional

from unstract.prompt_service.constants import FileStorageKeys


class EnvLoader:
    @staticmethod
    def get_env_or_die(env_key: str, default: Optional[str] = None) -> str:
        env_value = os.environ.get(env_key, default=default)
        if env_value is None or env_value == "":
            raise ValueError(f"Env variable {env_key} is required")
        return env_value

    @staticmethod
    def load_provider_credentials() -> dict[str, Any]:
        cred_env_data: str = EnvLoader.get_env_or_die(
            env_key=FileStorageKeys.FILE_STORAGE_CREDENTIALS
        )
        credentials = json.loads(cred_env_data)
        provider_data: dict[str, Any] = {}
        provider_data[FileStorageKeys.FILE_STORAGE_PROVIDER] = credentials["provider"]
        provider_data[FileStorageKeys.FILE_STORAGE_CREDENTIALS] = credentials[
            "credentials"
        ]
        return provider_data
