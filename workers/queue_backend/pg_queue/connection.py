"""Direct Postgres connection for the PG-queue client.

The PG queue is the first worker component to open a *direct* Postgres
connection — workers otherwise reach state via the Internal API, with
Redis the only other direct store. It reuses the **backend's** ``DB_*``
env so the target follows the deployment: in cloud those vars point at
PgBouncer (connection pooling); in OSS / on-prem they point straight at
Postgres (UN-3533 decision).

``search_path`` is set to ``DB_SCHEMA`` so the bespoke
``pg_queue_message`` table and ``pg_queue_read`` function resolve in the
same schema the backend manages.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection


def create_pg_connection() -> PgConnection:
    """Open a direct Postgres connection using the backend's ``DB_*`` env.

    Env names and defaults mirror ``backend/settings/base.py`` so the
    queue connects to the same database/schema the backend manages.
    """
    schema = os.getenv("DB_SCHEMA", "unstract")
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "unstract-db"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "unstract_db"),
        user=os.getenv("DB_USER", "unstract_dev"),
        password=os.getenv("DB_PASSWORD", "unstract_pass"),
        options=f"-c search_path={schema}",
    )
