import os

from unstract.platform_service.constants import LogLevel
from unstract.platform_service.utils import EnvManager


class Env:
    INVALID_ORGANIZATOIN = "Invalid organization"
    INVALID_PAYLOAD = "Bad Request / No payload"
    BAD_REQUEST = "Bad Request"
    REDIS_HOST = EnvManager.get_required_setting("REDIS_HOST")
    REDIS_PORT = int(EnvManager.get_required_setting("REDIS_PORT", 6379))
    REDIS_USERNAME = os.environ.get("REDIS_USERNAME")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
    PG_BE_HOST = os.environ.get("PG_BE_HOST")
    PG_BE_PORT = int(os.environ.get("PG_BE_PORT", 5432))
    PG_BE_USERNAME = os.environ.get("PG_BE_USERNAME")
    PG_BE_PASSWORD = os.environ.get("PG_BE_PASSWORD")
    PG_BE_DATABASE = os.environ.get("PG_BE_DATABASE")
    ENCRYPTION_KEY = EnvManager.get_required_setting("ENCRYPTION_KEY")
    MODEL_PRICES_URL = EnvManager.get_required_setting("MODEL_PRICES_URL")
    MODEL_PRICES_TTL_IN_DAYS = int(
        EnvManager.get_required_setting("MODEL_PRICES_TTL_IN_DAYS")
    )
    MODEL_PRICES_FILE_PATH = EnvManager.get_required_setting("MODEL_PRICES_FILE_PATH")
    APPLICATION_NAME = EnvManager.get_required_setting(
        "APPLICATION_NAME", "unstract-platform-service"
    )
    DB_SCHEMA = EnvManager.get_required_setting("DB_SCHEMA", "unstract_v2")
    LOG_LEVEL = EnvManager.get_required_setting("LOG_LEVEL", LogLevel.INFO)


EnvManager.raise_for_missing_envs()
