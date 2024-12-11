import os
from typing import Any, Optional
from urllib.parse import quote_plus

from backend.constants import FeatureFlag

# Requires PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python env setting
# to be loaded prior.
from unstract.flags.feature_flag import check_feature_flag_status

missing_settings = []


def get_required_setting(
    setting_key: str, default: Optional[Any] = None
) -> Optional[str]:
    """Get the value of an environment variable specified by the given key. Add
    missing keys to `missing_settings` so that exception can be raised at the
    end.

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
        missing_settings.append(setting_key)
    return data


DB_NAME = os.environ.get("DB_NAME", "unstract_db")
DB_USER = os.environ.get("DB_USER", "unstract_dev")
DB_HOST = os.environ.get("DB_HOST", "backend-db-1")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "unstract_pass")
DB_PORT = os.environ.get("DB_PORT", 5432)
if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    DB_ENGINE = "django.db.backends.postgresql"
else:
    DB_ENGINE = "django_tenants.postgresql_backend"


REDIS_USER = os.environ.get("REDIS_USER", "default")
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "unstract-redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "")

ENABLE_LOG_HISTORY = get_required_setting("ENABLE_LOG_HISTORY")
LOG_HISTORY_CONSUMER_INTERVAL = int(
    get_required_setting("LOG_HISTORY_CONSUMER_INTERVAL", "60")
)
LOGS_BATCH_LIMIT = int(get_required_setting("LOGS_BATCH_LIMIT", "30"))

CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://frontend.unstract.localhost",
    # Other allowed origins if needed
]

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": DB_ENGINE,
        "NAME": f"{DB_NAME}",
        "USER": f"{DB_USER}",
        "HOST": f"{DB_HOST}",
        "PASSWORD": f"{DB_PASSWORD}",
        "PORT": f"{DB_PORT}",
        "ATOMIC_REQUESTS": True,
    }
}

# SocketIO connection manager
SOCKET_IO_MANAGER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}"

CELERY_BROKER_URL = get_required_setting(
    "CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}"
)
# CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
# Postgres as result backend
CELERY_RESULT_BACKEND = (
    f"db+postgresql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_RETRY_BACKOFF = 60  # Time in seconds before retrying the task


INSTALLED_APPS = ["django.contrib.contenttypes", "django_celery_beat"]
