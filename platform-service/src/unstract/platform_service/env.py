import os

from unstract.platform_service.constants import LogLevel
from unstract.platform_service.utils import EnvManager


class Env:
    INVALID_ORGANIZATOIN = "Invalid organization"
    INVALID_PAYLOAD = "Bad Request / No payload"
    BAD_REQUEST = "Bad Request"
    REDIS_HOST = EnvManager.get_required_setting("REDIS_HOST")
    REDIS_PORT = int(EnvManager.get_required_setting("REDIS_PORT", 6379))
    REDIS_USER = os.environ.get("REDIS_USER")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
    DB_HOST = os.environ.get("DB_HOST")
    DB_PORT = int(os.environ.get("DB_PORT", 5432))
    DB_USER = os.environ.get("DB_USER")
    DB_PASSWORD = os.environ.get("DB_PASSWORD")
    DB_NAME = os.environ.get("DB_NAME")
    ENCRYPTION_KEY = EnvManager.get_required_setting("ENCRYPTION_KEY")
    MODEL_PRICES_URL = EnvManager.get_required_setting("MODEL_PRICES_URL")
    MODEL_PRICES_TTL_IN_DAYS = int(
        EnvManager.get_required_setting("MODEL_PRICES_TTL_IN_DAYS")
    )
    MODEL_PRICES_FILE_PATH = EnvManager.get_required_setting("MODEL_PRICES_FILE_PATH")
    APPLICATION_NAME = EnvManager.get_required_setting(
        "APPLICATION_NAME", "unstract-platform-service"
    )
    DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA")
    LOG_LEVEL = EnvManager.get_required_setting("LOG_LEVEL", LogLevel.INFO)


EnvManager.raise_for_missing_envs()
