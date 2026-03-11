import os

from unstract.platform_service.constants import LogLevel
from unstract.platform_service.utils import EnvManager


class Env:
    INVALID_ORGANIZATOIN = "Invalid organization"
    INVALID_PAYLOAD = "Bad Request / No payload"
    BAD_REQUEST = "Bad Request"
    REDIS_HOST = EnvManager.get_required_setting("REDIS_HOST")
    REDIS_PORT = int(EnvManager.get_required_setting("REDIS_PORT", 6379))
    # REDIS_USER/PASSWORD are optional (local Redis often has no auth)
    REDIS_USER = os.environ.get("REDIS_USER") or os.environ.get("REDIS_USERNAME")
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
    # DB vars: new names with fallback to legacy PG_BE_* names for rolling deploys
    DB_HOST = EnvManager.get_required_setting("DB_HOST", os.environ.get("PG_BE_HOST"))
    DB_PORT = int(
        EnvManager.get_required_setting("DB_PORT", os.environ.get("PG_BE_PORT", "5432"))
    )
    DB_USER = EnvManager.get_required_setting("DB_USER", os.environ.get("PG_BE_USERNAME"))
    DB_PASSWORD = EnvManager.get_required_setting(
        "DB_PASSWORD", os.environ.get("PG_BE_PASSWORD")
    )
    DB_NAME = EnvManager.get_required_setting("DB_NAME", os.environ.get("PG_BE_DATABASE"))
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
