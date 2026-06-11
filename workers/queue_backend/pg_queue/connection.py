"""Direct Postgres connection for the PG-queue client.

The PG queue is the first worker component to open a *direct* Postgres
connection — workers otherwise reach state via the Internal API, with
Redis the only other direct store. It reuses the **backend's** ``DB_*``
env so the target follows the deployment: in cloud those vars point at
PgBouncer (connection pooling); in OSS / on-prem they point straight at
Postgres (UN-3533 decision).

``search_path`` is set to ``DB_SCHEMA`` so the bespoke
``pg_queue_message`` table resolves in the same schema the backend
manages.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger(__name__)


def create_pg_connection(env_prefix: str = "DB_") -> PgConnection:
    """Open a direct Postgres connection from ``{env_prefix}*`` env.

    The default ``DB_`` prefix reads the same variable *names* the backend
    uses (``DB_HOST`` / ``DB_PORT`` / ``DB_NAME`` / ``DB_USER`` /
    ``DB_PASSWORD`` / ``DB_SCHEMA``), so the queue connects to the
    backend's database and schema. Tests pass ``env_prefix="TEST_DB_"`` to
    target a dev DB. The fallbacks below are dev-compose values (the host
    is the compose service name); real deployments always set the env
    explicitly, so the fallback host intentionally differs from the
    backend's own ``base.py`` default.
    """
    host = os.getenv(f"{env_prefix}HOST", "unstract-db")
    port = os.getenv(f"{env_prefix}PORT", "5432")
    dbname = os.getenv(f"{env_prefix}NAME", "unstract_db")
    user = os.getenv(f"{env_prefix}USER", "unstract_dev")
    schema = os.getenv(f"{env_prefix}SCHEMA", "unstract")
    try:
        return psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=os.getenv(f"{env_prefix}PASSWORD", "unstract_pass"),
            options=f"-c search_path={schema}",
        )
    except psycopg2.OperationalError:
        # First direct-DB worker component — make the failure self-identifying
        # so a misconfigured DB_* var is obvious. Secrets (password) omitted.
        logger.error(
            "PG-queue: failed to connect to Postgres "
            "(host=%s port=%s dbname=%s schema=%s, env_prefix=%r)",
            host,
            port,
            dbname,
            schema,
            env_prefix,
        )
        raise
