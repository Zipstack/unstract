"""Unit tests for the PG-queue schema qualifier (queue_backend.pg_queue.schema).

The qualifier is what lets the worker's raw SQL resolve its tables through
PgBouncer transaction pooling (which strips the ``search_path`` startup param) —
so these guard that the schema is read from ``DB_SCHEMA``, validated, rendered as
a quoted ``"<schema>".<table>`` prefix, and that no production query forgets to
go through it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from queue_backend.pg_queue.schema import QUEUE_TABLES, qualified, queue_schema


class TestQueueSchema:
    def test_defaults_to_unstract_when_unset(self, monkeypatch):
        monkeypatch.delenv("DB_SCHEMA", raising=False)
        assert queue_schema() == "unstract"

    def test_reads_db_schema(self, monkeypatch):
        monkeypatch.setenv("DB_SCHEMA", "acme")
        assert queue_schema() == "acme"

    def test_honours_env_prefix(self, monkeypatch):
        # The integration suite connects via TEST_DB_* — the qualifier must be
        # able to follow the same prefix the connection used.
        monkeypatch.setenv("TEST_DB_SCHEMA", "test_tenant")
        assert queue_schema(env_prefix="TEST_DB_") == "test_tenant"

    @pytest.mark.parametrize(
        "bad", ["pg_queue; DROP TABLE x", "a.b", "1schema", "has space", '"quoted"', ""]
    )
    def test_rejects_non_identifier_schema(self, monkeypatch, bad):
        # Defence-in-depth: an operator typo / hostile value must fail loud, not
        # build injectable or malformed SQL.
        monkeypatch.setenv("DB_SCHEMA", bad)
        with pytest.raises(ValueError, match="not a valid SQL identifier"):
            queue_schema()


class TestQualified:
    def test_quotes_schema_and_appends_table(self, monkeypatch):
        monkeypatch.setenv("DB_SCHEMA", "acme")
        assert qualified("pg_queue_message") == '"acme".pg_queue_message'

    def test_default_schema(self, monkeypatch):
        monkeypatch.delenv("DB_SCHEMA", raising=False)
        assert qualified("pg_task_result") == '"unstract".pg_task_result'

    def test_propagates_schema_validation(self, monkeypatch):
        monkeypatch.setenv("DB_SCHEMA", "bad;schema")
        with pytest.raises(ValueError, match="not a valid SQL identifier"):
            qualified("pg_queue_message")

    def test_rejects_unknown_table(self, monkeypatch):
        # A typo'd / unregistered table must fail loud rather than build a query
        # against a non-existent relation.
        monkeypatch.setenv("DB_SCHEMA", "acme")
        with pytest.raises(ValueError, match="not a known queue table"):
            qualified("pg_queue_mesage")  # typo

    def test_every_registered_table_qualifies(self, monkeypatch):
        monkeypatch.setenv("DB_SCHEMA", "acme")
        for table in QUEUE_TABLES:
            assert qualified(table) == f'"acme".{table}'


# Production modules that run raw queue SQL. Globbed (not hardcoded) so a NEW
# module under queue_backend/ is automatically covered by the guard below.
_WORKERS_ROOT = Path(__file__).resolve().parent.parent
_PROD_SQL_DIR = _WORKERS_ROOT / "queue_backend"


class TestNoBareTableGuard:
    """Fail the build if any production query names a queue table WITHOUT going
    through :func:`qualified`.

    A bare ``FROM/INTO/UPDATE pg_<table>`` resolves via ``search_path`` — which
    works in OSS/local (direct Postgres) but is stripped by PgBouncer in cloud →
    ``UndefinedTable``. So such a slip passes local tests and only breaks in
    cloud; this static guard is what makes "forgetting to qualify" un-mergeable.
    """

    def test_no_unqualified_queue_table_reference(self):
        # SQL keywords are uppercase by convention here, so the case-sensitive
        # match ignores lowercase prose / docstrings. A qualified use reads
        # ``FROM {qualified('pg_x')}`` — the table name never follows the keyword
        # directly, so only BARE references match.
        tables = "|".join(sorted(QUEUE_TABLES))
        bare = re.compile(rf"\b(?:FROM|INTO|UPDATE)\s+(?:{tables})\b")
        offenders: list[str] = []
        for path in sorted(_PROD_SQL_DIR.rglob("*.py")):
            for m in bare.finditer(path.read_text()):
                rel = path.relative_to(_WORKERS_ROOT)
                offenders.append(f"{rel}: {m.group(0)!r}")
        assert not offenders, (
            "Unqualified queue-table reference(s) — wrap the table with "
            "queue_backend.pg_queue.schema.qualified():\n" + "\n".join(offenders)
        )
