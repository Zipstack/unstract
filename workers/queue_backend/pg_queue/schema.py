"""Schema-qualified table names for the bespoke PG queue.

The queue's tables (``pg_queue_message``, ``pg_task_result``,
``pg_barrier_state``, ``pg_batch_dedup``, ``pg_orchestration_claim``,
``pg_orchestrator_lock``, ``pg_periodic_schedule``) live in the schema the
backend manages
(``DB_SCHEMA`` — ``unstract`` on-prem, a per-developer schema such as ``ali``
in cloud dev).

**Why the SQL must name the schema explicitly** instead of relying on
``search_path``: in cloud the worker connects through PgBouncer, which strips
the ``options=-c search_path=…`` startup parameter
(``IGNORE_STARTUP_PARAMETERS=options``), so the connection never gets the
queue's schema on its path and bare table names resolve to the default
(``public``) → ``UndefinedTable``. Transaction pooling also wouldn't preserve a
``SET search_path`` between statements. Qualifying every table as
``"<schema>".<table>`` makes the SQL self-contained, so it works through the
PgBouncer **transaction** pool unchanged — the same way the Celery result
backend reaches its ``public`` tables.

The schema is read at call time (not import) from the same ``{prefix}SCHEMA``
env the connection uses (:func:`create_pg_connection`), so the qualified name
always matches where the connection looks.
"""

from __future__ import annotations

import os
import re

# DB_SCHEMA is operator-supplied (helm values / env), never user input — but we
# still validate it as a bare SQL identifier before interpolating it into SQL,
# as defence-in-depth so a typo'd/hostile value can't become injection.
# re.ASCII keeps ``\w`` ASCII-only — a bare ``\w`` is Unicode-aware and would
# widen this identifier check to accented letters, defeating the purpose.
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$", re.ASCII)

# Mirror create_pg_connection's default so an unset DB_SCHEMA qualifies to the
# same schema the connection targets (search_path default ``unstract``).
_DEFAULT_SCHEMA = "unstract"

# Single source of truth for the bespoke queue tables. Every raw query qualifies
# its table THROUGH :func:`qualified`, which rejects any name not listed here — so
# a typo fails loud, and a genuinely new table forces an explicit addition. The
# no-bare-table guard test (tests/test_pg_schema.py) reads this same set, so the
# registry and the lint stay in lockstep.
QUEUE_TABLES = frozenset(
    {
        "pg_queue_message",
        "pg_task_result",
        "pg_barrier_state",
        "pg_batch_dedup",
        "pg_orchestration_claim",
        "pg_orchestrator_lock",
        "pg_periodic_schedule",
    }
)


def queue_schema(env_prefix: str = "DB_") -> str:
    """Return the validated queue schema from ``{env_prefix}SCHEMA``.

    Raises ``ValueError`` if the configured schema is not a plain SQL
    identifier — failing loud at the first query beats silently building
    injectable or malformed SQL.
    """
    schema = os.getenv(f"{env_prefix}SCHEMA", _DEFAULT_SCHEMA)
    if not _IDENT_RE.match(schema):
        raise ValueError(
            f"PG queue: {env_prefix}SCHEMA={schema!r} is not a valid SQL "
            "identifier (expected [A-Za-z_][A-Za-z0-9_]*)"
        )
    return schema


def qualified(table: str, env_prefix: str = "DB_") -> str:
    """Return ``"<schema>".<table>`` for use in the queue's raw SQL.

    ``table`` must be one of :data:`QUEUE_TABLES` — an unknown name (typo, or a
    new table not yet registered) raises, so it can never silently produce a
    query against the wrong/non-existent relation. Only the schema is quoted (it
    can be a reserved word or mixed case); the table names are fixed lowercase
    identifiers owned by this module.
    """
    if table not in QUEUE_TABLES:
        raise ValueError(
            f"PG queue: {table!r} is not a known queue table. Add it to "
            "QUEUE_TABLES (the single registry) if it is genuinely new."
        )
    return f'"{queue_schema(env_prefix)}".{table}'
