import os
from typing import Optional


class EnvManager:
    missing_settings: list[str] = []

    @classmethod
    def get_required_setting(
        cls, setting_key: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Get the value of an environment variable specified by the given key.
        Add missing keys to `missing_settings` so that exception can be raised
        at the end.

        Args:
            key (str): The key of the environment variable
            default (Optional[str], optional): Default value to return incase of
                env not found. Defaults to None.

        Returns:
            Optional[str]: The value of the environment variable if found,
                otherwise the default value.
        """
        data = os.environ.get(setting_key, default)
        if not data:
            cls.missing_settings.append(setting_key)
        return data

    @classmethod
    def raise_for_missing_envs(cls) -> None:
        """Raises an error if some settings are not configured.

        Raises:
            ValueError: Error mentioning envs which are not configured.
        """
        if cls.missing_settings:
            ERROR_MESSAGE = "Below required settings are missing.\n" + ",\n".join(
                cls.missing_settings
            )
            raise ValueError(ERROR_MESSAGE)
