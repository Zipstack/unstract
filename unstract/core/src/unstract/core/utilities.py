import logging
import os
from typing import Optional

logger = logging.getLogger()


class UnstractUtils:
    @staticmethod
    def get_env(env_key: str, default: Optional[str] = None, raise_err=False) -> str:
        """Returns the value of an env variable.

        If its empty or None, raises an error

        Args:
            env_key (str): Key to retrieve
            default (Optional[str], optional): Default for env if not defined.
                Defaults to None.
            raise_err (bool, optional): Flag to raise error if not defined.
                Defaults to False.

        Returns:
            str: Value of the env
        """
        env_value = os.environ.get(env_key, default)
        if env_value is None or env_value == "" and raise_err:
            raise RuntimeError(f"Env variable {env_key} is required")
        return env_value

    @staticmethod
    def build_tool_container_name(
        tool_image: str, tool_version: str, run_id: str
    ) -> str:
        container_name = f"{tool_image.split('/')[-1]}-{tool_version}-{run_id}"

        # To support limits of container clients like K8s
        if len(container_name) > 63:
            logger.warning(
                f"Container name exceeds 63 char limit for '{container_name}', "
                "truncating to 63 chars. There might be collisions in container names"
            )
        return container_name[:63]
