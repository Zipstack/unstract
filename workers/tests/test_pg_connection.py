"""Tests for ``create_pg_connection``'s bounded connect-retry.

Connecting is side-effect-free, so a *transient* ``OperationalError`` is
retried with exponential backoff (the common cloud blip: DB restart,
PgBouncer pool wait, brief network partition). Non-transient errors raise
immediately, and the enqueue INSERT is intentionally NOT retried elsewhere
(double-dispatch risk) — these tests pin the connect-layer contract only.

``psycopg2.connect`` and ``time.sleep`` are patched on the module, so no DB
and no real waiting.
"""

from __future__ import annotations

import psycopg2
import pytest
from queue_backend.pg_queue import connection as conn_mod


def _patch(monkeypatch, *, connect, retries="3", backoff="0.5"):
    """Patch connect + sleep; return the list that records sleep durations."""
    monkeypatch.setattr(conn_mod.psycopg2, "connect", connect)
    sleeps: list[float] = []
    monkeypatch.setattr(conn_mod.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setenv("WORKER_PG_QUEUE_CONNECT_RETRIES", retries)
    monkeypatch.setenv("WORKER_PG_QUEUE_CONNECT_BACKOFF", backoff)
    return sleeps


class TestCreatePgConnectionRetry:
    def test_succeeds_first_try_without_sleeping(self, monkeypatch):
        sentinel = object()
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            return sentinel

        sleeps = _patch(monkeypatch, connect=connect)
        assert conn_mod.create_pg_connection() is sentinel
        assert len(calls) == 1
        assert sleeps == []

    def test_retries_transient_then_succeeds(self, monkeypatch):
        sentinel = object()
        seq: list = [
            psycopg2.OperationalError("nope"),
            psycopg2.OperationalError("nope"),
            sentinel,
        ]

        def connect(**_kwargs):
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        sleeps = _patch(monkeypatch, connect=connect)
        assert conn_mod.create_pg_connection() is sentinel
        # Slept before attempts 2 and 3 with exponential backoff (0.5, 1.0).
        assert sleeps == [0.5, 1.0]

    def test_exhausts_attempts_and_raises(self, monkeypatch):
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            raise psycopg2.OperationalError("down")

        sleeps = _patch(monkeypatch, connect=connect, retries="3", backoff="0.1")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert len(calls) == 3  # all attempts used
        assert len(sleeps) == 2  # no sleep after the final attempt

    def test_non_operational_error_is_not_retried(self, monkeypatch):
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            raise psycopg2.ProgrammingError("bad options string")

        sleeps = _patch(monkeypatch, connect=connect)
        with pytest.raises(psycopg2.ProgrammingError):
            conn_mod.create_pg_connection()
        assert len(calls) == 1  # raised on the first attempt
        assert sleeps == []

    def test_single_attempt_when_retries_is_one(self, monkeypatch):
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            raise psycopg2.OperationalError("down")

        sleeps = _patch(monkeypatch, connect=connect, retries="1")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert len(calls) == 1
        assert sleeps == []

    def test_invalid_retries_env_falls_back_to_default(self, monkeypatch):
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            raise psycopg2.OperationalError("down")

        # Garbage RETRIES → default of 3 attempts (a bad knob must not wedge it).
        sleeps = _patch(monkeypatch, connect=connect, retries="abc", backoff="0.1")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert len(calls) == 3
        assert len(sleeps) == 2

    def test_unset_env_uses_production_defaults(self, monkeypatch):
        # The _patch helper always sets both knobs; this drives the real default
        # path (env absent → 3 attempts / 0.5s base) that production actually uses.
        monkeypatch.delenv("WORKER_PG_QUEUE_CONNECT_RETRIES", raising=False)
        monkeypatch.delenv("WORKER_PG_QUEUE_CONNECT_BACKOFF", raising=False)
        monkeypatch.setattr(
            conn_mod.psycopg2,
            "connect",
            lambda **_kwargs: (_ for _ in ()).throw(psycopg2.OperationalError("down")),
        )
        sleeps: list[float] = []
        monkeypatch.setattr(conn_mod.time, "sleep", lambda s: sleeps.append(s))
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert sleeps == [0.5, 1.0]  # default base 0.5, 3 attempts → 2 sleeps

    def test_backoff_grows_geometrically(self, monkeypatch):
        def connect(**_kwargs):
            raise psycopg2.OperationalError("down")

        # 4 attempts, base 1 → [1, 2, 4] — pins geometric (not linear) growth.
        sleeps = _patch(monkeypatch, connect=connect, retries="4", backoff="1")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert sleeps == [1.0, 2.0, 4.0]

    def test_sleep_is_capped_at_backoff_cap(self, monkeypatch):
        def connect(**_kwargs):
            raise psycopg2.OperationalError("down")

        # base 4 doubles past the 5.0s ceiling: 4, 8→5, 16→5, 32→5.
        sleeps = _patch(monkeypatch, connect=connect, retries="5", backoff="4")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert sleeps == [4.0, 5.0, 5.0, 5.0]

    def test_negative_backoff_clamped_to_zero(self, monkeypatch):
        def connect(**_kwargs):
            raise psycopg2.OperationalError("down")

        # Negative base → clamped to 0.0 (retry without sleep), not silently kept.
        sleeps = _patch(monkeypatch, connect=connect, retries="3", backoff="-1")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert sleeps == [0.0, 0.0]

    def test_invalid_backoff_env_falls_back_to_default(self, monkeypatch):
        def connect(**_kwargs):
            raise psycopg2.OperationalError("down")

        sleeps = _patch(monkeypatch, connect=connect, retries="3", backoff="xyz")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert sleeps == [0.5, 1.0]  # default base 0.5

    def test_retries_above_max_is_clamped(self, monkeypatch):
        calls: list[int] = []

        def connect(**_kwargs):
            calls.append(1)
            raise psycopg2.OperationalError("down")

        # 100 attempts requested → clamped to the 10-attempt ceiling (9 sleeps).
        sleeps = _patch(monkeypatch, connect=connect, retries="100", backoff="0.01")
        with pytest.raises(psycopg2.OperationalError):
            conn_mod.create_pg_connection()
        assert len(calls) == 10
        assert len(sleeps) == 9

    def test_connection_params_forwarded_and_stable_across_retries(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "pg.test")
        monkeypatch.setenv("DB_NAME", "mydb")
        monkeypatch.setenv("DB_SCHEMA", "myschema")
        sentinel = object()
        seq: list = [
            psycopg2.OperationalError("x"),
            psycopg2.OperationalError("x"),
            sentinel,
        ]
        calls: list[dict] = []

        def connect(**kwargs):
            calls.append(kwargs)
            item = seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        _patch(monkeypatch, connect=connect)
        assert conn_mod.create_pg_connection() is sentinel
        assert len(calls) == 3
        # The DB_* params (incl. the search_path options) are forwarded and
        # identical on every retry.
        assert all(c["options"] == "-c search_path=myschema" for c in calls)
        assert all(c["host"] == "pg.test" and c["dbname"] == "mydb" for c in calls)
