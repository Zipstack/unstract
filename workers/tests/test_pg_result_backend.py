"""Real-PG tests for PgResultBackend — the executor RPC result store.

DB-gated via the ``pg_conn`` fixture (skips when Postgres is unreachable or the
``pg_queue`` migration isn't applied). Pins the request-reply contract: store/get
round-trip (completed + failed), idempotent first-write-wins, absent -> None,
wait returns when present, wait times out, and wait picks up a late write from
*another* connection (the cross-process request-reply path).
"""

import logging
import os
import threading
import time
import uuid
from unittest.mock import MagicMock

import psycopg2
import psycopg2.errors
import pytest
from queue_backend.pg_queue.connection import create_pg_connection
from queue_backend.pg_queue.connection import is_connection_dead
from queue_backend.pg_queue.result_backend import (
    _SIGNAL_REDIS,
    _STORE_RETRY_BACKOFF_SECONDS,
    ERROR_TEXT_UNSTORABLE,
    PAYLOAD_UNSTORABLE_ERROR,
    STATUS_COMPLETED,
    STATUS_FAILED,
    PgResultBackend,
)

_MARK = "pgtaskresult-test"


def _key() -> str:
    return f"{_MARK}-{uuid.uuid4()}"


def _expires_at(pg_conn, task_id):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT expires_at FROM pg_task_result WHERE task_id = %s", (task_id,)
        )
        row = cur.fetchone()
    return row[0] if row else None


@pytest.fixture
def result_backend(pg_conn):
    rb = PgResultBackend(conn=pg_conn)
    yield rb
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM pg_task_result WHERE task_id LIKE %s", (f"{_MARK}-%",))
    pg_conn.commit()


class TestStoreGet:
    def test_store_completed_round_trips(self, result_backend):
        k = _key()
        result_backend.store_result(k, result={"success": True, "data": {"x": 1}})
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"] == {"success": True, "data": {"x": 1}}
        assert row["error"] == ""  # no-NULL text convention

    def test_store_failed_round_trips(self, result_backend):
        k = _key()
        result_backend.store_result(k, error="boom")
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_FAILED
        assert row["error"] == "boom"
        assert row["result"] is None

    def test_store_empty_dict_result_is_completed(self, result_backend):
        # UN-3693: ide-callback status-only writes pass result={} (a non-None empty
        # dict). store_result must record COMPLETED (its `result is not None` check),
        # not FAILED — an `if result:` regression would flip every successful PG
        # prompt to failed with the REST task_status poll reading "failed".
        k = _key()
        result_backend.store_result(k, result={})
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"] == {}

    def test_nul_in_result_still_delivers_the_result(self, result_backend):
        # UN-4126: LLMWhisperer `native_text` returns the PDF's embedded text
        # layer verbatim, so a NUL reaches the extracted output. json.dumps
        # encodes it \x00, which jsonb refuses -> store_result raised, the
        # consumer logged-and-acked, and the caller waited out its full 3600s
        # RPC timeout on work that had already succeeded. The row must land, and
        # land as COMPLETED: the work is done, and a NUL carries no meaning
        # worth failing an execution over.
        k = _key()
        result_backend.store_result(
            k, result={"success": True, "data": {"output": {"invoice_number": "POZF\x00BBOK"}}}
        )
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"]["data"]["output"]["invoice_number"] == "POZFBBOK"

    def test_valid_surrogate_pair_survives_the_round_trip(self, result_backend):
        # Guards the sanitiser against over-reach. The value must be built as an
        # actual high+low PAIR: a CPython str holds an astral character as ONE
        # code point (chr(0x1F600)), which a naive [high-low] class does not
        # match at all — so writing the emoji directly makes this test pass under
        # the very bug it claims to catch. A pair does reach Python from
        # surrogatepass decoding, jsonb ACCEPTS it (Postgres combines the halves),
        # and the naive class would delete both.
        k = _key()
        pair = chr(0xD83D) + chr(0xDE00)  # U+1F600 as its two surrogate halves
        result_backend.store_result(k, result={"note": f"done {pair}"})
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"]["note"] == f"done {chr(0x1F600)}"  # combined by PG

    def test_nul_in_error_text_still_writes_a_failed_row(self, result_backend):
        # The `error` column is `text`, which rejects a NUL exactly as jsonb
        # does — and an extraction error can embed document content.
        k = _key()
        result_backend.store_result(k, error="failed on \x00 byte")
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_FAILED
        assert row["error"] == "failed on  byte"

    def test_unstorable_result_degrades_to_failed_not_a_hang(self, result_backend):
        # NaN is deliberately NOT repaired (null/0 would corrupt the value), so
        # this is the fallback path: a row must still appear, so the caller gets
        # an error in seconds instead of waiting out EXECUTOR_RESULT_TIMEOUT.
        k = _key()
        result_backend.store_result(k, result={"confidence": float("nan")})
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_FAILED
        assert row["result"] is None
        assert "could not be stored" in row["error"]

    def test_absent_returns_none(self, result_backend):
        assert result_backend.get_result(_key()) is None

    def test_store_idempotent_first_write_wins(self, result_backend):
        """At-least-once redelivery must not clobber a recorded result."""
        k = _key()
        result_backend.store_result(k, result={"v": "first"})
        result_backend.store_result(k, error="second")  # ON CONFLICT DO NOTHING
        row = result_backend.get_result(k)
        assert row["status"] == STATUS_COMPLETED
        assert row["result"] == {"v": "first"}


class TestWait:
    def test_wait_returns_immediately_when_present(self, result_backend):
        k = _key()
        result_backend.store_result(k, result={"ok": True})
        row = result_backend.wait_for_result(k, timeout=5)
        assert row is not None
        assert row["result"] == {"ok": True}

    def test_wait_times_out_returns_none(self, result_backend):
        start = time.monotonic()
        row = result_backend.wait_for_result(_key(), timeout=1, poll_interval=0.2)
        assert row is None
        assert time.monotonic() - start >= 0.9  # waited ~the full timeout

    def test_wait_picks_up_late_write_from_other_conn(self, result_backend):
        """The real request-reply path: the waiter polls on its connection while
        the result is committed from a separate connection mid-wait.
        """
        k = _key()
        os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
        writer = PgResultBackend(conn=create_pg_connection(env_prefix="TEST_DB_"))

        def write_after_delay() -> None:
            time.sleep(0.6)
            writer.store_result(k, result={"late": True})

        t = threading.Thread(target=write_after_delay)
        t.start()
        try:
            row = result_backend.wait_for_result(k, timeout=10, poll_interval=0.2)
        finally:
            t.join()
            writer.close()
        assert row is not None
        assert row["result"] == {"late": True}


class TestForget:
    """forget() drops the consumed payload but keeps the row as a tombstone, so a
    redelivery can't re-insert it and the reaper still flushes it at expires_at.
    """

    def test_forget_nulls_result_keeps_row_and_preserves_expiry(
        self, result_backend, pg_conn
    ):
        k = _key()
        result_backend.store_result(k, result={"data": {"pii": "secret"}})
        before = _expires_at(pg_conn, k)
        result_backend.forget(k)
        row = result_backend.get_result(k)
        assert row is not None  # row kept (tombstone), not deleted
        assert row["result"] is None  # payload dropped
        assert row["status"] == STATUS_COMPLETED  # status preserved
        # expires_at untouched — the reaper must still delete at the ORIGINAL TTL,
        # so a future edit that also SETs expires_at would (correctly) fail this.
        assert _expires_at(pg_conn, k) == before

    def test_forget_clears_error_channel_too(self, result_backend):
        """Failed replies store error text that can embed document content, so the
        PII scrub must clear ``error`` as well — not just the success payload.
        """
        k = _key()
        result_backend.store_result(k, error="boom: <customer doc snippet>")
        result_backend.forget(k)
        row = result_backend.get_result(k)
        assert row is not None
        assert row["error"] == ""  # error text scrubbed
        assert row["result"] is None
        assert row["status"] == STATUS_FAILED  # status still distinguishes outcome

    def test_forget_absent_is_clean_noop(self, result_backend, caplog):
        """An absent row is a clean UPDATE-matches-nothing, NOT a swallowed error:
        because forget() catches Exception, a broken UPDATE would look identical to
        success — so pin that NO warning fires here (the UPDATE really ran).
        """
        with caplog.at_level(logging.WARNING):
            result_backend.forget(_key())  # must not raise
        assert "could not clear result" not in caplog.text

    def test_forget_blocks_redelivery_repopulation(self, result_backend):
        """After forget, an at-least-once redelivery of the executor message must
        not bring the payload back — the tombstone wins ON CONFLICT DO NOTHING.
        """
        k = _key()
        result_backend.store_result(k, result={"pii": "first"})
        result_backend.forget(k)
        result_backend.store_result(k, result={"pii": "again"})  # redelivery
        assert result_backend.get_result(k)["result"] is None  # stays cleared

    def test_forget_is_best_effort_logs_and_swallows(self, monkeypatch, caplog):
        """Contract is *logged AND swallowed*: a failure that survives the retry
        must not propagate (it runs inside dispatch's except->failure guard AFTER
        the caller holds the result) AND must emit the WARNING — a silent
        ``contextlib.suppress`` refactor would break the log-based alert and this
        pins against it.
        """
        rb = PgResultBackend()
        monkeypatch.setattr(
            rb,
            "_store_with_reconnect",
            MagicMock(side_effect=psycopg2.OperationalError("dead")),
        )
        with caplog.at_level(logging.WARNING):
            rb.forget("task-xyz")  # must NOT raise
        assert "could not clear result" in caplog.text
        assert "task-xyz" in caplog.text


# --- Unit: store_result reconnect-retry on a stale cached connection (UN-3659) ---


class _CursorCtx:
    """Mimic a psycopg2 cursor used as a context manager."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *_):
        return False


class TestStoreResultNeverStrands:
    """UN-4126 strand-prevention, asserted WITHOUT Postgres.

    These live here rather than beside their DB-backed siblings on purpose: the
    real-Postgres tests carry the `integration` marker and route to
    `integration-workers`, which is `optional: true` and cannot turn CI red. The
    contract these assert — a finished task never leaves the caller waiting out
    EXECUTOR_RESULT_TIMEOUT — is the whole point of the fix, so it belongs in the
    gating `unit-workers` lane.
    """

    @staticmethod
    def _conn(*, execute_side_effect=None):
        cur = MagicMock()
        if execute_side_effect is not None:
            cur.execute.side_effect = execute_side_effect
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        return conn, cur

    def test_result_payload_is_sanitised_before_the_jsonb_cast(self):
        # Gating cover for the ENCODER at this sink. The DB round-trip that
        # proves repair lives in `integration-workers`, which is `optional: true`
        # and cannot turn CI red — so reverting `dumps_for_jsonb` to `json.dumps`
        # here would regress the UN-4126 hang with a green build. Assert the
        # parameter handed to the driver instead, which needs no Postgres.
        conn, cur = self._conn()
        PgResultBackend(conn=conn).store_result(
            "k", result={"output": {"invoice_number": "POZF\x00BBOK"}}
        )
        result_param = cur.execute.call_args.args[1][2]
        assert "\\u0000" not in result_param
        assert "POZFBBOK" in result_param

    def test_error_text_is_sanitised_before_the_insert(self):
        # Same, for the failure channel: `error` is a `text` column, which
        # rejects a NUL exactly as jsonb does, and extraction error messages can
        # embed document content.
        conn, cur = self._conn()
        PgResultBackend(conn=conn).store_result("k", error="failed on \x00 byte")
        error_param = cur.execute.call_args.args[1][3]
        assert "\x00" not in error_param
        assert error_param == "failed on  byte"

    def test_a_rejected_result_degrades_with_the_completed_discriminator(
        self, monkeypatch
    ):
        # The other half of the pair. A task that finished must NOT be recorded
        # with the retry-is-safe text, or a recovery pass would re-run an
        # executor task that already cost a full LLM spend.
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        calls = {"n": 0}

        def execute(sql, params):
            calls["n"] += 1
            if calls["n"] == 1:
                raise psycopg2.errors.ProgramLimitExceeded("result too long")

        conn, cur = self._conn(execute_side_effect=execute)
        PgResultBackend(conn=conn).store_result("k", result={"output": "x" * 10})

        degraded_text = cur.execute.call_args.args[1][3]
        assert degraded_text == PAYLOAD_UNSTORABLE_ERROR
        assert degraded_text != ERROR_TEXT_UNSTORABLE

    def test_rejected_error_text_also_degrades_to_a_row(self, monkeypatch):
        # The failure branch must carry the same net as the success branch: a
        # payload rejection on the `error` column previously escaped with no row
        # written, which is the UN-4126 strand reached from the failure channel.
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        statuses: list[str] = []
        calls = {"n": 0}

        def execute(sql, params):
            statuses.append(params[1])
            calls["n"] += 1
            if calls["n"] == 1:
                raise psycopg2.errors.ProgramLimitExceeded("error text too long")

        conn, cur = self._conn(execute_side_effect=execute)
        PgResultBackend(conn=conn).store_result("k", error="x" * 10)
        assert statuses == [STATUS_FAILED, STATUS_FAILED], "no degraded row written"
        # ...and it must say the task FAILED, not that it completed. The two
        # texts are the retry discriminator and they point opposite ways, so
        # writing the completed one here would tell recovery logic the work was
        # already paid for and suppress a retry that is correct.
        degraded_text = cur.execute.call_args.args[1][3]
        assert degraded_text == ERROR_TEXT_UNSTORABLE
        assert degraded_text != PAYLOAD_UNSTORABLE_ERROR

    def test_oversized_result_still_records_a_failed_row(self, monkeypatch):
        # ProgramLimitExceeded ("string too long", SQLSTATE 54) subclasses
        # OperationalError, NOT DataError — so a `except psycopg2.DataError`
        # net misses it, the reconnect-retry misreads it as a dead connection,
        # and the caller strands. The degraded row must still land.
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        attempts: list[str] = []

        def execute(sql, params):
            attempts.append(params[1])  # status
            if params[1] == STATUS_COMPLETED:
                raise psycopg2.errors.ProgramLimitExceeded("string too long")

        conn, _ = self._conn(execute_side_effect=execute)
        PgResultBackend(conn=conn).store_result("k", result={"big": "x"})
        assert STATUS_FAILED in attempts, "no degraded row written — caller strands"

    def test_unencodable_result_still_records_a_failed_row(self):
        # A circular reference now surfaces as ValueError (see unstract.core.jsonb);
        # RecursionError would slip past the encode seam and strand the caller.
        cycle: dict = {}
        cycle["self"] = cycle
        statuses: list[str] = []
        conn, _ = self._conn(
            execute_side_effect=lambda sql, params: statuses.append(params[1])
        )
        PgResultBackend(conn=conn).store_result("k", result=cycle)
        assert statuses == [STATUS_FAILED]

    def test_waiter_is_signalled_even_when_store_raises(self, monkeypatch):
        # Pins the `finally`, and ONLY the `finally`: the injected error must be
        # one `_write_outcome` does NOT catch, so it propagates out of the try
        # and the signal can only fire from the `finally`. (An error inside
        # _PAYLOAD_REJECTED_ERRORS would be swallowed into a degraded row and
        # `_write_outcome` would return normally — then a plain trailing
        # statement would signal too, and this test would assert nothing.)
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend._signal_backend",
            lambda: _SIGNAL_REDIS,
        )
        signalled: list[str] = []
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend._signal_ready",
            lambda key: signalled.append(key),
        )
        conn, _ = self._conn(
            execute_side_effect=psycopg2.OperationalError("database is down")
        )
        rb = PgResultBackend(conn=conn)  # injected -> no reconnect retry
        with pytest.raises(psycopg2.OperationalError):
            rb.store_result("k", result={"a": 1})
        assert signalled == ["k"], "signal did not fire on the raising path"

    def test_waiter_is_signalled_when_even_the_degraded_row_fails(self, monkeypatch):
        # The swallowing path: every write fails but nothing propagates, so the
        # caller must still be woken rather than left for its full timeout.
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend._signal_backend",
            lambda: _SIGNAL_REDIS,
        )
        signalled: list[str] = []
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend._signal_ready",
            lambda key: signalled.append(key),
        )
        conn, _ = self._conn(
            execute_side_effect=psycopg2.errors.ProgramLimitExceeded("too long")
        )
        PgResultBackend(conn=conn).store_result("k", result={"a": 1})
        assert signalled == ["k"]



class TestPayloadRejectionIsNotAConnectionDeath:
    """``ProgramLimitExceeded`` ("string too long", SQLSTATE 54) subclasses
    ``OperationalError``, so it is a member of BOTH ``CONN_DEAD_ERRORS`` and
    ``PAYLOAD_REJECTED_ERRORS``. Classified by ``isinstance`` alone it reads as a
    dead connection: the handle is discarded, a reconnect happens, and a write
    that can never land is re-sent — a second pass over a payload that is, by the
    nature of this error, very large. ``is_connection_dead`` tests the payload
    family first; these pin that.
    """

    def test_an_oversized_payload_is_not_read_as_a_dead_connection(self):
        oversized = psycopg2.errors.ProgramLimitExceeded("too long")
        assert isinstance(oversized, psycopg2.OperationalError)  # the trap itself
        assert is_connection_dead(oversized) is False

    def test_a_real_connection_error_still_reads_as_dead(self):
        assert is_connection_dead(psycopg2.OperationalError("server closed")) is True
        assert is_connection_dead(psycopg2.InterfaceError("closed")) is True

    def test_a_plain_data_error_is_not_read_as_a_dead_connection(self):
        assert is_connection_dead(psycopg2.DataError("bad jsonb")) is False

    def test_an_oversized_result_is_written_once_not_re_sent(self, monkeypatch):
        # The behavioural half: one INSERT attempt, no reconnect, and the row
        # still degrades so the caller is not stranded.
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.errors.ProgramLimitExceeded("too long")
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        factory = MagicMock()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.time.sleep", MagicMock()
        )
        rb = PgResultBackend()
        rb._conn = conn  # a cached, owned connection — retry-eligible if dead

        rb.store_result("k", result={"output": "x" * 10})

        factory.assert_not_called()  # no pointless reconnect
        conn.close.assert_not_called()  # the connection was never condemned
        # One rejected INSERT, then the degraded row — not two rejected INSERTs.
        assert cur.execute.call_count == 2
        degraded = cur.execute.call_args.args[1]
        assert degraded[1] == "failed"
        assert degraded[3] == PAYLOAD_UNSTORABLE_ERROR



class TestStoreResultReconnectRetry:
    """store_result self-heals a connection PgBouncer reaped while the executor
    sat idle — the exec-b11ba2f3 hang. Idempotent (ON CONFLICT), so the retry is
    unconditional (no reused-vs-fresh guard, unlike PgQueueClient.send).
    """

    @staticmethod
    def _conn(*, execute_side_effect=None):
        cur = MagicMock()
        if execute_side_effect is not None:
            cur.execute.side_effect = execute_side_effect
        conn = MagicMock()
        conn.closed = 0
        conn.cursor.return_value = _CursorCtx(cur)
        return conn, cur

    @staticmethod
    def _no_sleep(monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr("queue_backend.pg_queue.result_backend.time.sleep", sleep)
        return sleep

    # Both outcomes go through the same write path — the PR's whole point is that
    # a *failed* task's result (error=) is delivered too, not silently dropped.
    @pytest.mark.parametrize(
        "outcome",
        [{"result": {"ok": True}}, {"error": "boom"}],
        ids=["completed", "failed"],
    )
    def test_stale_conn_retries_and_writes_result(self, monkeypatch, outcome):
        # Cached owned conn reaped while idle fails its first INSERT; the one-shot
        # retry reconnects (factory) and the result is written + committed.
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("idle reap"))
        fresh, fresh_cur = self._conn()
        factory = MagicMock(return_value=fresh)
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()  # owns its connection
        rb._conn = dead  # simulate a cached (reused) connection

        rb.store_result("k", **outcome)

        dead.close.assert_called_once()  # stale conn discarded
        factory.assert_called_once()  # reconnected exactly once
        fresh_cur.execute.assert_called_once()  # the retry INSERT ran
        fresh.commit.assert_called_once()

    def test_commit_time_reap_retries(self, monkeypatch):
        # An idle reap usually surfaces when the buffered INSERT flushes at
        # conn.commit() (after the cursor yield), not at execute() — that path
        # must retry too.
        dead, _ = self._conn()
        dead.commit.side_effect = psycopg2.OperationalError("reaped at commit")
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})  # must self-heal
        dead.close.assert_called_once()
        fresh.commit.assert_called_once()

    def test_injected_connection_not_retried(self, monkeypatch):
        # An injected (caller-owned) conn is never discarded by _cursor, so a
        # retry would re-acquire the same dead handle — short-circuit to re-raise
        # without the spurious backoff sleep.
        conn, _ = self._conn(execute_side_effect=psycopg2.OperationalError("dead"))
        factory = MagicMock()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend(conn=conn)  # injected -> not owned

        with pytest.raises(psycopg2.OperationalError):
            rb.store_result("k", result={"ok": True})
        factory.assert_not_called()
        sleep.assert_not_called()
        conn.close.assert_not_called()  # caller's connection untouched

    @pytest.mark.parametrize(
        "exc_type", [psycopg2.OperationalError, psycopg2.InterfaceError]
    )
    def test_retries_both_connection_dead_error_types(self, monkeypatch, exc_type):
        # InterfaceError ("connection already closed") is the other stale symptom;
        # narrowing the except to OperationalError alone would re-break the fix.
        dead, _ = self._conn(execute_side_effect=exc_type("dead"))
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})  # must not raise
        fresh.commit.assert_called_once()

    def test_backoff_fires_once_on_retry(self, monkeypatch):
        dead, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        fresh, _ = self._conn()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            MagicMock(return_value=fresh),
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead

        rb.store_result("k", result={"ok": True})
        sleep.assert_called_once_with(_STORE_RETRY_BACKOFF_SECONDS)

    def test_retry_also_fails_reraises_after_one_reconnect(self, monkeypatch):
        dead1, _ = self._conn(execute_side_effect=psycopg2.OperationalError("reap"))
        dead2, _ = self._conn(execute_side_effect=psycopg2.OperationalError("still"))
        factory = MagicMock(return_value=dead2)
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = dead1

        with pytest.raises(psycopg2.OperationalError):
            rb.store_result("k", result={"ok": True})
        factory.assert_called_once()  # exactly one reconnect, no loop

    def test_non_connection_error_not_retried(self, monkeypatch):
        # A logical error (not Operational/Interface) is not a stale-conn symptom.
        bad, _ = self._conn(execute_side_effect=RuntimeError("logic"))
        factory = MagicMock()
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection", factory
        )
        sleep = self._no_sleep(monkeypatch)
        rb = PgResultBackend()
        rb._conn = bad

        with pytest.raises(RuntimeError):
            rb.store_result("k", result={"ok": True})
        factory.assert_not_called()
        sleep.assert_not_called()


class TestStoreResultRealReconnect:
    """DB-gated: store_result REALLY reconnects against live PG (not just mock
    orchestration). Skips when Postgres is unreachable (pg_conn fixture). This is
    the test that fails if _cursor stopped nulling _conn or the reconnect handle
    were unusable — the mock tests can't see that.
    """

    def test_real_reconnect_heals_closed_connection(self, pg_conn, monkeypatch):
        # The owned backend reconnects via result_backend.create_pg_connection;
        # point that at the integration DB (TEST_DB_*), the same one pg_conn uses
        # (the bare DB_* env is the suite's unit-isolation placeholder).
        os.environ.setdefault("TEST_DB_HOST", "127.0.0.1")
        monkeypatch.setattr(
            "queue_backend.pg_queue.result_backend.create_pg_connection",
            lambda *a, **k: create_pg_connection(env_prefix="TEST_DB_"),
        )

        key = _key()
        rb = PgResultBackend()  # owned, real connection to the test DB
        try:
            _ = rb.conn  # materialise the connection
            rb._conn.close()  # client-side close -> InterfaceError on next use
            rb.store_result(key, result={"healed": True})  # must self-heal
        finally:
            rb.close()

        # The row really landed — read it back on the fixture's own connection.
        pg_conn.rollback()  # clear any aborted txn before reading
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT result->>'healed' FROM pg_task_result WHERE task_id = %s",
                (key,),
            )
            row = cur.fetchone()
            cur.execute("DELETE FROM pg_task_result WHERE task_id = %s", (key,))
        pg_conn.commit()
        assert row is not None and row[0] == "true"


class TestRedisDownFallbackBudget:
    """The early Redis-unavailable fallback in ``_wait_via_redis`` must degrade to
    the poll for the REMAINING budget, not the full original timeout — otherwise
    ``wait_for_result`` overshoots its stated timeout on the Redis-down path.
    (No DB/Redis needed: this pins the timeout arithmetic.)
    """

    def test_early_redis_unavailable_passes_remaining_budget(self, monkeypatch):
        import queue_backend.pg_queue.result_backend as rbmod

        rb = PgResultBackend(conn=MagicMock())
        # Initial get_result (pre-wait race check) misses → proceed to the fallback.
        monkeypatch.setattr(rb, "get_result", lambda task_id: None)
        # Redis unavailable up front, and deliberately burn ~0.1s of the budget
        # between the deadline being set and the fallback branch.
        def slow_no_redis():
            time.sleep(0.1)
            return None

        monkeypatch.setattr(rbmod, "_get_result_redis_client", slow_no_redis)

        captured = {}

        def fake_poll(task_id, timeout, poll_interval):
            captured["timeout"] = timeout
            return {"ok": True}

        monkeypatch.setattr(rb, "_poll_for_result", fake_poll)

        out = rb._wait_via_redis("t", timeout=5.0, poll_interval=0.2)
        assert out == {"ok": True}
        # Remaining budget, not the full 5.0 (buggy version passed exactly 5.0).
        assert 0 < captured["timeout"] < 5.0 - 0.05
