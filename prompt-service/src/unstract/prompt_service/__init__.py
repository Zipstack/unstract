from collections.abc import Generator
from contextlib import contextmanager
from os import environ as env
from typing import Any

from playhouse.postgres_ext import PostgresqlExtDatabase


def get_env_or_die(env_key: str) -> str:
    env_value = env.get(env_key)
    if not env_value:
        raise ValueError(f"Env variable {env_key} is required")
    return env_value


# Load required environment variables
db_host = get_env_or_die("PG_BE_HOST")
db_port = get_env_or_die("PG_BE_PORT")
db_user = get_env_or_die("PG_BE_USERNAME")
db_pass = get_env_or_die("PG_BE_PASSWORD")
db_name = get_env_or_die("PG_BE_DATABASE")

be_db = PostgresqlExtDatabase(
    db_name,
    user=db_user,
    password=db_pass,
    host=db_host,
    port=db_port,
)


@contextmanager
def db_context() -> Generator[PostgresqlExtDatabase, Any, None]:
    try:
        be_db.connect()
        yield be_db
    finally:
        if not be_db.is_closed():
            be_db.close()
