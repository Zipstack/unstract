"""Tests for the PG queue consumer (claim → run → ack).

Unit tests drive ``poll_once`` with a mocked client and *real* registered
Celery tasks (so ``apply()`` actually runs the body). The integration test
exercises the full enqueue → poll → execute → ack loop against real Postgres
(skips if unreachable / unmigrated).
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from celery import shared_task
from queue_backend.fairness import FAIRNESS_HEADER_NAME
from queue_backend.pg_queue import to_payload
from queue_backend.pg_queue.client import QueueMessage
from queue_backend.pg_queue.consumer import PgQueueConsumer

# Registered test tasks (namespaced). apply() runs their bodies in-process.
_calls: list = []


@shared_task(name="test_pg_consumer.ok")
def _ok_task(x, y=0):
    _calls.append((x, y))
    return x + y


@shared_task(name="test_pg_consumer.boom")
def _boom_task():
    raise RuntimeError("boom")


@shared_task(name="test_pg_consumer.dt")
def _dt_task():
    # Returns a non-JSON-native value (datetime) — the self-chain must coerce it
    # before enqueue, else client.send's plain json.dumps would raise.
    from datetime import datetime

    return {"when": datetime(2020, 1, 1)}  # noqa: DTZ001 — fixed value for the test


@pytest.fixture(autouse=True)
def _clear_calls():
    _calls.clear()


def _msg(msg_id, payload, *, read_ct=1):
    return QueueMessage(msg_id=msg_id, message=payload, read_ct=read_ct)


def _ok_payload(x, y=0):
    return {"task_name": "test_pg_consumer.ok", "args": [x], "kwargs": {"y": y}}


# --- poll_once (mocked client, real tasks) ---


class TestPollOnce:
    def test_runs_task_and_acks(self):
        client = MagicMock()
        client.read.return_value = [_msg(1, _ok_payload(3, 4))]
        assert PgQueueConsumer(["q"], client=client).poll_once() == 1
        assert _calls == [(3, 4)]  # task body ran
        client.delete.assert_called_once_with(1)  # acked

    def test_failed_task_is_not_acked_and_logs(self, caplog):
        client = MagicMock()
        client.read.return_value = [
            _msg(2, {"task_name": "test_pg_consumer.boom", "args": [], "kwargs": {}})
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_not_called()  # left for vt-expiry redelivery
        assert "failed" in caplog.text  # the cycling signal is logged

    def test_unknown_task_is_dropped(self, caplog):
        client = MagicMock()
        client.read.return_value = [
            _msg(3, {"task_name": "nope.nope", "args": [], "kwargs": {}})
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(3)  # dropped, not redelivered
        assert "unknown task" in caplog.text

    def test_missing_task_name_dropped_as_malformed(self, caplog):
        client = MagicMock()
        client.read.return_value = [_msg(4, {"args": [], "kwargs": {}})]  # no task_name
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(4)
        assert "missing task_name" in caplog.text  # distinct from "unknown task"

    def test_poison_message_dropped_past_max_attempts(self, caplog):
        client = MagicMock()
        # boom task, claimed more than max_attempts times → drop instead of redeliver.
        client.read.return_value = [
            _msg(5, {"task_name": "test_pg_consumer.boom"}, read_ct=6)
        ]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client, max_attempts=5).poll_once()
        client.delete.assert_called_once_with(5)  # dropped as poison
        assert "poison" in caplog.text

    def test_fairness_header_rebuilt_for_run(self):
        # Mock app so we can inspect the apply() headers.
        fairness = {"org_id": "o", "workload_type": "api", "pipeline_priority": 5}
        task = MagicMock()
        app = MagicMock()
        app.tasks.get.return_value = task
        client = MagicMock()
        client.read.return_value = [
            _msg(6, {"task_name": "t", "args": [1], "kwargs": {"k": "v"}, "fairness": fairness})
        ]
        PgQueueConsumer(["q"], client=client, app=app).poll_once()
        kwargs = task.apply.call_args.kwargs
        assert kwargs["args"] == [1]
        assert kwargs["kwargs"] == {"k": "v"}
        assert kwargs["headers"] == {FAIRNESS_HEADER_NAME: fairness}

    def test_ack_finding_no_row_warns(self, caplog):
        client = MagicMock()
        client.delete.return_value = False  # row already gone (vt expired mid-run)
        client.read.return_value = [_msg(7, _ok_payload(1))]
        with caplog.at_level(logging.WARNING, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client).poll_once()
        assert "possible double-run" in caplog.text

    def test_multi_message_batch(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(10, _ok_payload(1)),
            _msg(11, {"task_name": "test_pg_consumer.boom"}),
            _msg(12, {"task_name": "nope.nope"}),
            _msg(13, _ok_payload(2)),
        ]
        assert PgQueueConsumer(["q"], client=client).poll_once() == 4
        assert _calls == [(1, 0), (2, 0)]  # ok tasks ran in order
        deleted = {c.args[0] for c in client.delete.call_args_list}
        assert deleted == {10, 12, 13}  # ok acked + unknown dropped; boom NOT acked

    def test_empty_batch_acks_nothing(self):
        client = MagicMock()
        client.read.return_value = []
        assert PgQueueConsumer(["q"], client=client).poll_once() == 0
        client.delete.assert_not_called()


class TestConstruction:
    def test_rejects_non_positive_params(self):
        for kw in (
            {"batch_size": 0},
            {"vt_seconds": -1},
            {"poll_interval": 0},
            {"backoff_max": 0},
            {"max_attempts": 0},
        ):
            with pytest.raises(ValueError):
                PgQueueConsumer(["q"], client=MagicMock(), **kw)

    def test_rejects_backoff_max_below_poll_interval(self):
        # Otherwise backoff would shrink below poll_interval instead of growing.
        with pytest.raises(ValueError, match="backoff_max"):
            PgQueueConsumer(
                ["q"], client=MagicMock(), poll_interval=0.5, backoff_max=0.1
            )


class TestRunLoop:
    def test_run_stops_gracefully(self, monkeypatch):
        client = MagicMock()
        client.read.return_value = []  # always empty → backoff path
        consumer = PgQueueConsumer(["q"], client=client)
        # First empty poll → sleep (patched to request stop) → loop exits.
        monkeypatch.setattr(
            "queue_backend.pg_queue.consumer.time.sleep", lambda _s: consumer.stop()
        )
        consumer.run(install_signals=False)
        assert consumer._running is False

    def test_backoff_grows_then_resets(self, monkeypatch):
        client = MagicMock()
        # empty, empty, one message, empty → backoff doubles, resets, doubles.
        client.read.side_effect = [[], [], [_msg(1, _ok_payload(1))], []]
        consumer = PgQueueConsumer(
            ["q"], client=client, poll_interval=0.1, backoff_max=0.25
        )
        sleeps: list[float] = []

        def _sleep(secs):
            sleeps.append(secs)
            if len(sleeps) == 3:  # stop after the third sleep
                consumer.stop()

        monkeypatch.setattr("queue_backend.pg_queue.consumer.time.sleep", _sleep)
        consumer.run(install_signals=False)
        # empty→0.1, empty→0.2 (doubled), [msg] resets, empty→0.1 again.
        assert sleeps == [0.1, 0.2, 0.1]

    def test_poll_error_does_not_kill_loop(self, monkeypatch):
        client = MagicMock()
        # first poll raises (transient), then empty → loop must survive the raise.
        client.read.side_effect = [RuntimeError("blip"), []]
        consumer = PgQueueConsumer(["q"], client=client)
        sleeps: list[float] = []

        def _sleep(secs):
            sleeps.append(secs)
            if len(sleeps) == 2:  # stop after the post-error poll
                consumer.stop()

        monkeypatch.setattr("queue_backend.pg_queue.consumer.time.sleep", _sleep)
        consumer.run(install_signals=False)  # must not raise
        assert client.read.call_count == 2  # kept polling after the error

    def test_run_refuses_to_start_with_empty_registry(self):
        # A non-bootstrapped consumer would drop every message as "unknown" —
        # fail loudly instead.
        from celery import Celery

        empty_app = Celery("empty-no-tasks")  # only celery.* built-ins
        consumer = PgQueueConsumer(["q"], client=MagicMock(), app=empty_app)
        with pytest.raises(RuntimeError, match="no application tasks"):
            consumer.run(install_signals=False)

    def test_run_starts_with_registered_tasks(self, monkeypatch):
        # Positive arm: a non-empty registry starts and polls. current_app has
        # the module's @shared_task tasks registered, so the guard passes.
        client = MagicMock()
        client.read.return_value = []  # empty → loop sleeps → we stop it
        consumer = PgQueueConsumer(["q"], client=client)
        monkeypatch.setattr(
            "queue_backend.pg_queue.consumer.time.sleep", lambda _s: consumer.stop()
        )
        consumer.run(install_signals=False)  # must not raise
        assert client.read.called

    def test_run_bypasses_guard_when_require_tasks_false(self, monkeypatch):
        # require_tasks=False skips the guard even on an empty registry (lets a
        # caller opt out, e.g. a deliberately task-less smoke run).
        from celery import Celery

        empty_app = Celery("empty-no-tasks")
        client = MagicMock()
        client.read.return_value = []
        consumer = PgQueueConsumer(["q"], client=client, app=empty_app)
        monkeypatch.setattr(
            "queue_backend.pg_queue.consumer.time.sleep", lambda _s: consumer.stop()
        )
        consumer.run(install_signals=False, require_tasks=False)  # must not raise
        assert client.read.called

    def test_registered_task_count_excludes_celery_builtins(self):
        # The guard counts application tasks only — celery.* built-ins (present
        # in every app) must not mask an un-bootstrapped registry.
        from celery import Celery

        empty_app = Celery("empty-no-tasks")
        assert (
            PgQueueConsumer(["q"], client=MagicMock(), app=empty_app)._registered_task_count()
            == 0
        )

        @empty_app.task(name="test_pg_consumer.demo")
        def _demo():
            return 1

        assert (
            PgQueueConsumer(["q"], client=MagicMock(), app=empty_app)._registered_task_count()
            == 1
        )


# --- Liveness heartbeat (drives the health endpoint) ---


class TestPollHeartbeat:
    def test_poll_once_refreshes_heartbeat(self):
        client = MagicMock()
        client.read.return_value = []
        consumer = PgQueueConsumer(["q"], client=client)
        # Simulate a long-idle consumer, then poll → heartbeat resets to ~now.
        consumer._last_poll_monotonic -= 120
        assert consumer.seconds_since_last_poll() > 100
        consumer.poll_once()
        assert consumer.seconds_since_last_poll() < 1.0

    def test_heartbeat_stamped_before_read(self):
        # Pins the headline design: the stamp lands at the TOP of poll_once
        # (before read), so a task running longer than the threshold still trips
        # the probe. A bottom-of-poll stamp would pass test_poll_once_refreshes
        # but fail here.
        client = MagicMock()
        consumer = PgQueueConsumer(["q"], client=client)
        before = consumer._last_poll_monotonic
        seen: dict[str, float] = {}
        client.read.side_effect = lambda *a, **k: (
            seen.setdefault("during", consumer._last_poll_monotonic),
            [],
        )[1]
        consumer.poll_once()
        assert seen["during"] > before  # refreshed BEFORE read ran, not after

    def test_is_poll_stale_threshold(self):
        consumer = PgQueueConsumer(["q"], client=MagicMock())
        consumer._last_poll_monotonic -= 120  # last poll 120s ago
        assert consumer.is_poll_stale(60) is True  # past threshold → stale
        assert consumer.is_poll_stale(200) is False  # within threshold → fresh

    def test_fresh_consumer_is_not_stale(self):
        # Seeded at construction, so a just-started consumer reads healthy.
        consumer = PgQueueConsumer(["q"], client=MagicMock())
        assert consumer.is_poll_stale(60) is False

    def test_health_server_disabled_without_port(self):
        # No port configured → no server bound (opt-in).
        from queue_backend.pg_queue.consumer import _maybe_start_health_server

        consumer = PgQueueConsumer(["q"], client=MagicMock())
        assert _maybe_start_health_server(consumer, port=None, stale_after=60) is None

    def test_liveness_server_reports_200_then_503(self):
        # Real endpoint: 200 while the poll loop is fresh, 503 once it goes
        # stale. Bind port 0 so the OS picks a free port (no fixed-port clash).
        import json
        import urllib.error
        import urllib.request

        from queue_backend.pg_queue.consumer import LivenessServer

        consumer = PgQueueConsumer(["q"], client=MagicMock())
        server = LivenessServer(consumer, port=0, stale_after=60)
        server.start()
        try:
            url = f"http://127.0.0.1:{server.bound_port}/health"
            with urllib.request.urlopen(url, timeout=5) as resp:
                assert resp.status == 200
                assert json.loads(resp.read())["status"] == "healthy"

            consumer._last_poll_monotonic -= 120  # force the loop stale
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(url, timeout=5)
            assert ei.value.code == 503
            assert json.loads(ei.value.read())["status"] == "unhealthy"
        finally:
            server.stop()

    def test_liveness_aliases_and_unknown_path(self):
        # All three probe aliases answer 200 (different orchestrators probe
        # different paths); an unknown path is 404 (guards against a regression
        # that makes every path pass).
        import urllib.error
        import urllib.request

        from queue_backend.pg_queue.consumer import LivenessServer

        consumer = PgQueueConsumer(["q"], client=MagicMock())
        server = LivenessServer(consumer, port=0, stale_after=60)
        server.start()
        try:
            base = f"http://127.0.0.1:{server.bound_port}"
            # Aliases, plus a query string (self.path includes it) must match.
            for path in ("/health", "/healthz", "/livez", "/health?probe=k8s"):
                with urllib.request.urlopen(f"{base}{path}", timeout=5) as resp:
                    assert resp.status == 200, path
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(f"{base}/nope", timeout=5)
            assert ei.value.code == 404
        finally:
            server.stop()

    def test_double_start_is_rejected(self):
        from queue_backend.pg_queue.consumer import LivenessServer

        server = LivenessServer(PgQueueConsumer(["q"], client=MagicMock()), port=0, stale_after=60)
        server.start()
        try:
            with pytest.raises(RuntimeError, match="already started"):
                server.start()
        finally:
            server.stop()
        # stop() returns it to the inert state → can start again.
        server.start()
        server.stop()


# --- Integration: full enqueue → poll → execute → ack against real PG ---
# Uses the shared ``pg_client`` fixture from conftest.py.


class TestConsumerIntegration:
    def test_enqueue_poll_execute_ack(self, pg_client):
        queue_name = f"test_consumer_{os.getpid()}"
        try:
            pg_client.send(
                queue_name,
                to_payload("test_pg_consumer.ok", args=[5], kwargs={"y": 6}),
            )
            claimed = PgQueueConsumer([queue_name], client=pg_client).poll_once()
            assert claimed == 1
            assert (5, 6) in _calls  # task actually executed off Postgres
            # Row was acked (deleted) — nothing left to claim.
            assert pg_client.read(queue_name, vt_seconds=30, qty=10) == []
        finally:
            with pg_client.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM pg_queue_message WHERE queue_name = %s", (queue_name,)
                )
            pg_client.conn.commit()


class TestMultiQueue:
    """9f: one consumer drains several queues round-robin."""

    def test_round_robin_reads_each_queue_and_aggregates(self):
        client = MagicMock()
        # qa → 2 msgs, qb → 1 msg; poll_once returns the total across both.
        client.read.side_effect = [
            [_msg(1, _ok_payload(1)), _msg(2, _ok_payload(2))],
            [_msg(3, _ok_payload(3))],
        ]
        claimed = PgQueueConsumer(["qa", "qb"], client=client).poll_once()
        assert claimed == 3
        # Read once per queue, in order.
        assert [c.args[0] for c in client.read.call_args_list] == ["qa", "qb"]

    def test_empty_queue_does_not_starve_the_others(self):
        client = MagicMock()
        client.read.side_effect = [[], [_msg(1, _ok_payload(1))]]
        assert PgQueueConsumer(["empty", "busy"], client=client).poll_once() == 1

    def test_rejects_empty_queue_list(self):
        with pytest.raises(ValueError, match="queue_names"):
            PgQueueConsumer([], client=MagicMock())

    def test_one_queue_failing_does_not_abort_the_others(self):
        """A read failure on one queue is isolated: the already-acked work this
        cycle still counts (so run() doesn't take the empty backoff path), and
        the failure doesn't propagate out of poll_once."""
        client = MagicMock()
        client.read.side_effect = [[_msg(1, _ok_payload(1))], RuntimeError("boom")]
        claimed = PgQueueConsumer(["qa", "qb"], client=client).poll_once()
        assert claimed == 1  # qa's message counted despite qb raising
        assert _calls == [(1, 0)]  # qa task body ran
        client.delete.assert_called_once_with(1)  # qa acked

    def test_read_uses_batch_size_qty_per_queue(self):
        client = MagicMock()
        client.read.return_value = []
        PgQueueConsumer(["qa", "qb"], client=client, batch_size=2).poll_once()
        assert [c.kwargs["qty"] for c in client.read.call_args_list] == [2, 2]

    def test_duplicate_queues_are_deduped(self):
        """A duplicate (e.g. env "q,q") must not double-read the same queue."""
        client = MagicMock()
        client.read.return_value = []
        consumer = PgQueueConsumer(["q", "q"], client=client)
        assert consumer.queue_names == ["q"]
        consumer.poll_once()
        assert client.read.call_count == 1


def test_parse_queue_list():
    from queue_backend.pg_queue.consumer import _parse_queue_list

    assert _parse_queue_list("a") == ["a"]  # single value → one-element (back-compat)
    assert _parse_queue_list("a,b,c") == ["a", "b", "c"]
    assert _parse_queue_list(" a , b ,c ") == ["a", "b", "c"]  # whitespace stripped
    assert _parse_queue_list("a,,b") == ["a", "b"]  # empties dropped


class TestRequestReply:
    """Executor-RPC reply_key behaviour: store outcome + ack after one attempt;
    drop branches store a definitive failure; a store failure still acks (no
    expensive re-run). PgResultBackend is mocked so no DB is needed.
    """

    _RB = "queue_backend.pg_queue.consumer.PgResultBackend"

    def test_success_stores_result_and_acks(self):
        client = MagicMock()
        client.read.return_value = [_msg(1, {**_ok_payload(3, 4), "reply_key": "rk1"})]
        with patch(self._RB) as rb_cls:
            PgQueueConsumer(["q"], client=client).poll_once()
        rb = rb_cls.return_value
        rb.store_result.assert_called_once()
        assert rb.store_result.call_args.args[0] == "rk1"
        assert rb.store_result.call_args.kwargs["result"] == 7  # x + y
        assert rb.store_result.call_args.kwargs["error"] is None
        client.delete.assert_called_once_with(1)  # acked

    def test_task_raise_stores_error_and_acks(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(2, {"task_name": "test_pg_consumer.boom", "reply_key": "rk2"})
        ]
        with patch(self._RB) as rb_cls:
            PgQueueConsumer(["q"], client=client).poll_once()
        rb = rb_cls.return_value
        assert rb.store_result.call_args.kwargs["error"] is not None
        assert rb.store_result.call_args.kwargs["result"] is None
        client.delete.assert_called_once_with(2)  # acked, NOT left for redelivery

    def test_unknown_task_stores_error_and_acks(self):
        client = MagicMock()
        client.read.return_value = [
            _msg(3, {"task_name": "nope.nope", "reply_key": "rk3"})
        ]
        with patch(self._RB) as rb_cls:
            PgQueueConsumer(["q"], client=client).poll_once()
        rb = rb_cls.return_value
        assert rb.store_result.call_args.kwargs["error"] is not None
        client.delete.assert_called_once_with(3)

    def test_store_failure_on_success_path_still_acks(self, caplog):
        client = MagicMock()
        client.read.return_value = [_msg(4, {**_ok_payload(1, 1), "reply_key": "rk4"})]
        with patch(self._RB) as rb_cls:
            rb_cls.return_value.store_result.side_effect = RuntimeError("db down")
            with caplog.at_level(
                logging.ERROR, logger="queue_backend.pg_queue.consumer"
            ):
                PgQueueConsumer(["q"], client=client).poll_once()
        # A store failure must NOT block the ack (avoids an expensive re-run).
        client.delete.assert_called_once_with(4)
        assert "FAILED to store request-reply result" in caplog.text


class TestSelfChain:
    """Async/callback self-chaining (③c): with no reply_key, the consumer enqueues
    the on_success / on_error continuation onto its queue after the task runs, then
    acks regardless (a vt-redelivery would re-run the executor = LLM double-spend).
    Best-effort: a chain-enqueue failure still acks. ``client.send`` is the
    self-chain enqueue (the mock client is also read/delete).
    """

    @staticmethod
    def _spec(task="cb.done", queue="ide_callback"):
        return {
            "task_name": task,
            "kwargs": {"callback_kwargs": {"room": "r1"}},
            "queue": queue,
        }

    def test_success_chains_on_success_with_result_and_acks(self):
        client = MagicMock()
        payload = {**_ok_payload(3, 4), "on_success": self._spec(), "task_id": "tid"}
        client.read.return_value = [_msg(1, payload)]
        PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(1)  # executor msg acked
        client.send.assert_called_once()  # continuation enqueued
        queue_arg, payload_arg = client.send.call_args.args[:2]
        assert queue_arg == "ide_callback"
        assert payload_arg["task_name"] == "cb.done"
        assert payload_arg["args"] == [7]  # x + y prepended (Celery link parity)
        assert payload_arg["kwargs"] == {"callback_kwargs": {"room": "r1"}}

    def test_failure_chains_on_error_with_task_id_and_acks(self):
        client = MagicMock()
        payload = {
            "task_name": "test_pg_consumer.boom",
            "on_error": self._spec("cb.err"),
            "task_id": "tid-9",
        }
        client.read.return_value = [_msg(2, payload)]
        PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(2)  # acked, NOT left for redelivery
        client.send.assert_called_once()
        payload_arg = client.send.call_args.args[1]
        assert payload_arg["task_name"] == "cb.err"
        assert payload_arg["args"] == ["tid-9"]  # dispatch task_id as the failed id
        # The real error text rides callback_kwargs['error'] (no Celery AsyncResult
        # to recover it from on PG) so on_error callbacks surface it, not a default.
        assert "RuntimeError: boom" in payload_arg["kwargs"]["callback_kwargs"]["error"]

    def test_early_drop_branches_still_chain_on_error(self):
        # Critical: a dispatch_with_callback that hits malformed/unknown/poison must
        # still fire on_error — else the HTTP-202 caller hangs with no terminal event.
        err = self._spec("cb.err")
        cases = [
            # (msg_id, payload, read_ct)  — malformed / unknown / poison
            (10, {"on_error": err, "task_id": "t"}, 1),
            (11, {"task_name": "nope.nope", "on_error": err, "task_id": "t"}, 1),
            (12, {"task_name": "test_pg_consumer.boom", "on_error": err, "task_id": "t"}, 99),
        ]
        for msg_id, payload, read_ct in cases:
            client = MagicMock()
            client.read.return_value = [_msg(msg_id, payload, read_ct=read_ct)]
            PgQueueConsumer(["q"], client=client).poll_once()
            client.delete.assert_called_once_with(msg_id)  # dropped/acked
            client.send.assert_called_once()  # on_error STILL chained
            payload_arg = client.send.call_args.args[1]
            assert payload_arg["task_name"] == "cb.err"
            assert payload_arg["args"] == ["t"]
            assert payload_arg["kwargs"]["callback_kwargs"]["error"]  # the drop reason

    def test_non_json_safe_result_is_coerced_before_chaining(self):
        client = MagicMock()
        payload = {
            "task_name": "test_pg_consumer.dt",
            "on_success": self._spec(),
            "task_id": "tid",
        }
        client.read.return_value = [_msg(6, payload)]
        PgQueueConsumer(["q"], client=client).poll_once()
        client.send.assert_called_once()  # not swallowed by a json.dumps TypeError
        chained = client.send.call_args.args[1]["args"][0]
        assert isinstance(chained["when"], str)  # datetime → str (default=str)
        import json as _json

        _json.dumps(chained)  # the coerced payload is plain-json serialisable

    def test_on_success_only_failure_acks_not_redelivered(self):
        # An on_success-only callback dispatch (on_error omitted) whose executor
        # RAISES must ACK — not fall through to vt-redelivery and re-run the
        # executor (LLM double-spend). No on_error → nothing chained, but acked.
        client = MagicMock()
        payload = {
            "task_name": "test_pg_consumer.boom",
            "on_success": self._spec(),
            "task_id": "tid",
        }
        client.read.return_value = [_msg(7, payload)]
        PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(7)  # acked, NOT left for redelivery
        client.send.assert_not_called()  # success callback not fired on a raise

    def test_on_success_enqueue_failure_falls_back_to_on_error(self):
        # If the success hand-off can't be enqueued, surface on_error so the caller
        # still gets a terminal event instead of hanging after the LLM spend.
        client = MagicMock()
        client.send.side_effect = [RuntimeError("queue down"), 999]  # 1st fails, 2nd ok
        payload = {
            **_ok_payload(2, 2),
            "on_success": self._spec("cb.ok"),
            "on_error": self._spec("cb.err"),
            "task_id": "tid",
        }
        client.read.return_value = [_msg(8, payload)]
        PgQueueConsumer(["q"], client=client).poll_once()
        assert client.send.call_count == 2  # on_success attempt, then on_error fallback
        fallback = client.send.call_args_list[1].args[1]
        assert fallback["task_name"] == "cb.err"
        assert "delivery failed" in fallback["kwargs"]["callback_kwargs"]["error"]
        client.delete.assert_called_once_with(8)  # acked

    def test_no_continuation_is_plain_fire_and_forget(self):
        client = MagicMock()
        client.read.return_value = [_msg(3, _ok_payload(1, 1))]
        PgQueueConsumer(["q"], client=client).poll_once()
        client.send.assert_not_called()  # nothing self-chained
        client.delete.assert_called_once_with(3)  # acked

    def test_chain_failure_on_success_still_acks(self, caplog):
        client = MagicMock()
        client.send.side_effect = RuntimeError("queue down")
        payload = {**_ok_payload(2, 2), "on_success": self._spec()}
        client.read.return_value = [_msg(4, payload)]
        with caplog.at_level(logging.ERROR, logger="queue_backend.pg_queue.consumer"):
            PgQueueConsumer(["q"], client=client).poll_once()
        client.delete.assert_called_once_with(4)  # acked despite the chain failure
        assert "FAILED to self-chain" in caplog.text

    def test_continuation_org_extracted_from_context(self):
        # The chained callback inherits the executor request's org (context dict);
        # non-dict / absent args degrade to "" (callbacks aren't fairness-critical).
        org_of = PgQueueConsumer._continuation_org
        assert org_of({"args": [{"organization_id": "orgZ"}]}) == "orgZ"
        assert org_of({"args": [42]}) == ""
        assert org_of({}) == ""

    def test_reply_key_and_callback_are_mutually_exclusive(self):
        # The consumer checks reply_key first and would silently drop a callback —
        # so to_payload rejects the ambiguous combination at the build boundary.
        spec = self._spec()
        with pytest.raises(ValueError, match="mutually exclusive"):
            to_payload("execute_extraction", reply_key="rk", on_success=spec)
        with pytest.raises(ValueError, match="mutually exclusive"):
            to_payload("execute_extraction", reply_key="rk", on_error=spec)
        # Either alone is fine.
        assert to_payload("execute_extraction", reply_key="rk")["reply_key"] == "rk"
        assert to_payload("execute_extraction", on_success=spec)["on_success"] == spec


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
