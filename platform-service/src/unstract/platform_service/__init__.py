from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from playhouse.postgres_ext import PostgresqlExtDatabase
from unstract.platform_service.env import Env

be_db = PostgresqlExtDatabase(
    Env.PG_BE_DATABASE,
    user=Env.PG_BE_USERNAME,
    password=Env.PG_BE_PASSWORD,
    host=Env.PG_BE_HOST,
    port=Env.PG_BE_PORT,
)


@contextmanager
def db_context() -> Generator[PostgresqlExtDatabase, Any, None]:
    try:
        be_db.connect()
        yield be_db
    finally:
        if not be_db.is_closed():
            be_db.close()
