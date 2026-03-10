from collections.abc import Generator
from contextlib import contextmanager
from os import environ as env
from typing import Any

from playhouse.postgres_ext import PostgresqlExtDatabase

from unstract.prompt_service.utils.env_loader import get_env_or_die

# Load required environment variables
db_host = get_env_or_die("DB_HOST")
db_port = get_env_or_die("DB_PORT")
db_user = get_env_or_die("DB_USER")
db_pass = get_env_or_die("DB_PASSWORD")
db_name = get_env_or_die("DB_NAME")
application_name = env.get("APPLICATION_NAME", "unstract-prompt-service")

# Initialize and connect to the database
db = PostgresqlExtDatabase(
    database=db_name,
    user=db_user,
    host=db_host,
    password=db_pass,
    port=db_port,
    options=f"-c application_name={application_name}",
)


@contextmanager
def db_context() -> Generator[PostgresqlExtDatabase, Any, None]:
    try:
        db.connect()
        yield db
    finally:
        if not db.is_closed():
            db.close()
