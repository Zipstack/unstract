"""Characterisation tests for ``RedisDecrBarrier`` (PG Queue Phase 6b).

The risky behaviour-change PR replacing Celery's chord aggregation
primitive with the labs-design ``DECR remaining`` + ``RPUSH results``
pattern (see ``queue_backend/redis_barrier.py``).

Three layers:

1. **Protocol shape** — ``RedisDecrBarrier`` satisfies the ``Barrier``
   Protocol; the handle satisfies ``BarrierHandle``.
2. **Wire model** — ``enqueue`` initialises the per-execution counter
   + results list with TTL, stamps fairness on each header task,
   attaches the ``barrier_decr_and_check`` link, and dispatches via
   ``apply_async``.
3. **Link aggregation** — the ``barrier_decr_and_check`` task runs the
   atomic Lua script, fires the callback exactly when remaining reads
   0, passes the aggregated results, and respects fairness on the
   callback signature.

Redis is mocked via ``MagicMock`` — the contract under test is the
sequence of Redis ops + their args, not Redis's own correctness.
A future integration test (against a real Redis) would belong in
``test_redis_barrier_integration.py``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from queue_backend import (
    Barrier,
    BarrierHandle,
    RedisDecrBarrier,
    barrier_decr_and_check,
)
from queue_backend.fairness import FAIRNESS_HEADER_NAME, FairnessKey, WorkloadType
from queue_backend.redis_barrier import (
    _KEY_TTL_DEFAULT_SECONDS,
    _remaining_key,
    _results_key,
)


# --- Protocol shape ---


class TestRedisDecrBarrierProtocolShape:
    def test_satisfies_barrier_protocol(self):
        barrier: Barrier = RedisDecrBarrier()
        assert callable(getattr(barrier, "enqueue", None))

    def test_handle_satisfies_barrier_handle(self):
        from queue_backend.redis_barrier import _RedisBarrierHandle

        handle: BarrierHandle = _RedisBarrierHandle(id="exec-1")
        assert handle.id == "exec-1"
        assert isinstance(handle.id, str)


# --- Enqueue: wire model ---


@pytest.fixture
def redis_mock():
    """Mock the Redis client used by ``RedisDecrBarrier``."""
    return MagicMock(name="redis_client")


@pytest.fixture
def barrier(redis_mock):
    """``RedisDecrBarrier`` with an injected mock client.

    Production builds its client from env via ``create_redis_client``;
    tests inject so no Redis is required.
    """
    return RedisDecrBarrier(redis_client=redis_mock)


class TestRedisDecrBarrierEnqueue:
    def test_empty_header_returns_none_and_touches_no_redis(self, barrier, redis_mock):
        """Mirrors the ``CeleryChordBarrier`` zero-header contract:
        ``None`` is the *sole* signal of no-work-enqueued, and we
        don't pay the Redis round-trip for it."""
        result = barrier.enqueue(
            [],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        assert result is None
        # No SET / DELETE on the empty path — short-circuit before any
        # Redis round-trip.
        redis_mock.set.assert_not_called()
        redis_mock.delete.assert_not_called()

    def test_missing_execution_id_raises(self, barrier):
        """``RedisDecrBarrier`` uses ``execution_id`` as the key suffix
        for ``remaining:{exec_id}`` / ``results:{exec_id}``. Without
        it we can't isolate this execution's counter — fail loudly
        instead of routing into a global namespace collision."""
        header = [MagicMock(name="h1")]
        with pytest.raises(ValueError, match=r"execution_id"):
            barrier.enqueue(
                header,
                callback_task_name="cb",
                # No execution_id.
                callback_kwargs={"pipeline_id": "p-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )

    def test_initialises_remaining_counter_with_ttl(self, barrier, redis_mock):
        """``remaining:{exec_id}`` SET to ``len(header_tasks)`` with
        TTL — belt-and-suspenders cleanup if a link never fires for
        a task (e.g. worker crash mid-execution)."""
        header = [MagicMock(name="h1"), MagicMock(name="h2"), MagicMock(name="h3")]
        barrier.enqueue(
            header,
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-42"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        redis_mock.set.assert_called_once_with(
            _remaining_key("exec-42"),
            3,
            ex=_KEY_TTL_DEFAULT_SECONDS,
        )
        # ``results:{exec_id}`` AND ``abort_lock:{exec_id}`` are DEL'd
        # to clear any stale prior-run leftovers (e.g. from a retry
        # reusing the same execution_id). Without DELing the abort
        # lock here, a stale lock from a prior failed run would mask
        # a retry's failure as success.
        from queue_backend.redis_barrier import _abort_lock_key

        redis_mock.delete.assert_called_once_with(
            _results_key("exec-42"),
            _abort_lock_key("exec-42"),
        )

    def test_link_attached_to_each_header_task(self, barrier, redis_mock):
        """Every header task gets the ``barrier_decr_and_check`` link.
        Cloning (not mutating the caller's list) preserves the same
        guarantee ``CeleryChordBarrier`` makes for cross-tenant
        signature reuse."""
        h1 = MagicMock(name="h1")
        h2 = MagicMock(name="h2")
        barrier.enqueue(
            [h1, h2],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        # Each task cloned, .link(...) called once on the clone,
        # apply_async called once on the clone.
        h1.clone.assert_called_once_with()
        h2.clone.assert_called_once_with()
        h1.clone.return_value.link.assert_called_once()
        h2.clone.return_value.link.assert_called_once()
        h1.clone.return_value.apply_async.assert_called_once_with()
        h2.clone.return_value.apply_async.assert_called_once_with()
        # The caller's signatures were NOT mutated (no .link on the
        # originals).
        h1.link.assert_not_called()
        h2.link.assert_not_called()

    def test_fairness_header_stamped_on_each_header_task(self, barrier, redis_mock):
        """``fairness.as_header()`` rides on every header signature as
        an additive AMQP header — same wire shape as
        ``CeleryChordBarrier``'s fairness plumbing."""
        h1 = MagicMock(name="h1")
        fairness = FairnessKey(org_id="org-x", workload_type=WorkloadType.API)
        barrier.enqueue(
            [h1],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
            fairness=fairness,
        )
        # ``as_header()`` returns ``{FAIRNESS_HEADER_NAME: <dict>}``
        # (a nested dict, not a JSON string — see fairness.py:62).
        h1.clone.return_value.set.assert_called_once_with(
            headers=fairness.as_header()
        )

    def test_no_fairness_no_header_added(self, barrier, redis_mock):
        """When ``fairness=None``, no ``headers=`` kwarg on the
        signature — preserves wire equivalence for the
        non-fairness call path."""
        h1 = MagicMock(name="h1")
        barrier.enqueue(
            [h1],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        h1.clone.return_value.set.assert_not_called()

    def test_returns_handle_with_execution_id(self, barrier, redis_mock):
        """``BarrierHandle.id`` is the execution id — what call sites
        log for chord-id tracing. (Under ``CeleryChordBarrier`` this
        was the chord aggregator's AsyncResult id; under
        ``RedisDecrBarrier`` we don't have such a task, so we expose
        the execution id which is a stable per-execution identifier
        that the existing log consumers don't depend on the
        underlying type of.)"""
        result = barrier.enqueue(
            [MagicMock()],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-42"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        assert result is not None
        assert result.id == "exec-42"
        assert isinstance(result.id, str)

    def test_setup_failure_raises(self, barrier, redis_mock):
        """Any substrate failure (Redis down, network blip mid-setup)
        propagates as an exception — matches the ``Barrier`` Protocol:
        ``None`` is sole "no-op" signal, everything else raises."""
        redis_mock.set.side_effect = ConnectionError("redis is down")
        with pytest.raises(ConnectionError, match="redis is down"):
            barrier.enqueue(
                [MagicMock()],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )

    def test_default_ttl_is_six_hours(self):
        """Lock in the chosen default. Accidental shrinkage to a few
        minutes would cause spurious callback fires on any execution
        longer than the new value; accidental expansion to days would
        leak orphaned keys. The default reflects the worst-case
        ``FILE_PROCESSING_TASK_TIME_LIMIT`` (3h) x 2x margin."""
        assert _KEY_TTL_DEFAULT_SECONDS == 6 * 60 * 60

    def test_ttl_overridable_via_env(self, barrier, redis_mock, monkeypatch):
        """Operators with substantially longer (or shorter) workflows
        can override the cleanup TTL via ``WORKER_BARRIER_KEY_TTL_SECONDS``.

        Set well above the default to confirm the env-driven path is
        actually read (not the constant)."""
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", str(3 * 24 * 3600))
        barrier.enqueue(
            [MagicMock()],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        # ``ex=`` on the counter SET should be the overridden 3-day value.
        assert redis_mock.set.call_args.kwargs.get("ex") == 3 * 24 * 3600

    # Invalid-value handling tests live in ``TestTtlEnvValidation``
    # below — they now assert ``raises`` (matching ``get_barrier()``'s
    # loud-on-misconfig posture) rather than silent fallback.


# --- Link task: aggregation ---


class TestBarrierDecrAndCheckLink:
    """The ``barrier_decr_and_check`` worker task — the load-bearing
    aggregator. Runs after each header task and either decrements +
    aggregates (most calls) or fires the callback (the last call).
    """

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_pending_path_decrement_only(self, get_redis):
        """When the post-decrement counter reads >0, no callback
        dispatch — just ``RPUSH + DECR`` and return a pending status."""
        redis_client = MagicMock(name="redis")
        # Lua script returns [remaining, results-empty-list-since-pending].
        # ``register_script`` returns a callable that returns the script result.
        script = MagicMock(name="script", return_value=[2, []])
        redis_client.register_script.return_value = script
        get_redis.return_value = redis_client

        with patch("celery.current_app") as current_app:
            # Invoke the underlying function directly (bypass
            # Celery's @worker_task wrapper for unit testing).
            result = barrier_decr_and_check.run(
                {"batch_id": "b1", "status": "ok"},
                execution_id="exec-1",
                callback_descriptor={
                    "task_name": "cb",
                    "kwargs": {"execution_id": "exec-1"},
                    "queue": "q",
                    "fairness_headers": None,
                },
            )

        # Lua script invoked with the right keys + JSON-serialised
        # result + TTL seconds for the EXPIRE inside the script.
        script.assert_called_once()
        call_kwargs = script.call_args.kwargs
        assert call_kwargs["keys"] == [
            _remaining_key("exec-1"),
            _results_key("exec-1"),
        ]
        assert json.loads(call_kwargs["args"][0]) == {"batch_id": "b1", "status": "ok"}
        assert call_kwargs["args"][1] == _KEY_TTL_DEFAULT_SECONDS

        # No callback dispatch — remaining > 0.
        current_app.signature.assert_not_called()
        assert result == {"status": "pending", "remaining": 2}

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_complete_path_fires_callback_with_aggregated_results(self, get_redis):
        """When the post-decrement counter reads 0, the link reads the
        full results list (returned by the Lua script in the same
        atomic step), constructs the callback signature with the
        aggregated list as the first arg, and dispatches via
        ``apply_async``."""
        redis_client = MagicMock(name="redis")
        # Lua returns [0, [serialised result_1, result_2, result_3]].
        aggregated_raw = [
            json.dumps({"batch_id": "b1", "status": "ok"}),
            json.dumps({"batch_id": "b2", "status": "ok"}),
            json.dumps({"batch_id": "b3", "status": "ok"}),
        ]
        script = MagicMock(name="script", return_value=[0, aggregated_raw])
        redis_client.register_script.return_value = script
        get_redis.return_value = redis_client

        with patch("celery.current_app") as current_app:
            cb_sig = MagicMock(name="callback_signature")
            cb_sig.apply_async.return_value = MagicMock(id="callback-task-id-xyz")
            current_app.signature.return_value = cb_sig

            result = barrier_decr_and_check.run(
                {"batch_id": "b3", "status": "ok"},
                execution_id="exec-42",
                callback_descriptor={
                    "task_name": "process_batch_callback_api",
                    "kwargs": {
                        "execution_id": "exec-42",
                        "pipeline_id": "pipe-7",
                        "organization_id": "org-x",
                    },
                    "queue": "api_file_processing_callback",
                    "fairness_headers": None,
                },
            )

        # Callback signature constructed with aggregated results as
        # first arg, callback kwargs forwarded, queue pinned.
        current_app.signature.assert_called_once_with(
            "process_batch_callback_api",
            args=[
                [
                    {"batch_id": "b1", "status": "ok"},
                    {"batch_id": "b2", "status": "ok"},
                    {"batch_id": "b3", "status": "ok"},
                ],
            ],
            kwargs={
                "execution_id": "exec-42",
                "pipeline_id": "pipe-7",
                "organization_id": "org-x",
            },
            queue="api_file_processing_callback",
        )
        cb_sig.apply_async.assert_called_once_with()

        assert result["status"] == "complete"
        assert result["callback_task_id"] == "callback-task-id-xyz"
        assert result["aggregated_count"] == 3

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_complete_path_passes_fairness_header_to_callback(self, get_redis):
        """Fairness rides the callback signature too — same wire shape
        as ``CeleryChordBarrier``'s callback fairness plumbing."""
        redis_client = MagicMock(name="redis")
        script = MagicMock(name="script", return_value=[0, [json.dumps({"x": 1})]])
        redis_client.register_script.return_value = script
        get_redis.return_value = redis_client

        # Match the wire shape produced by ``FairnessKey.as_header()`` —
        # a nested dict, not a JSON string (see fairness.py:62).
        fairness_headers = {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-x",
                "workload_type": "non_api",
                "pipeline_priority": 5,
            }
        }
        with patch("celery.current_app") as current_app:
            current_app.signature.return_value = MagicMock(
                apply_async=MagicMock(return_value=MagicMock(id="cb-id"))
            )

            barrier_decr_and_check.run(
                {"x": 1},
                execution_id="exec-1",
                callback_descriptor={
                    "task_name": "cb",
                    "kwargs": {"execution_id": "exec-1"},
                    "queue": "q",
                    "fairness_headers": fairness_headers,
                },
            )

        # ``headers=fairness_headers`` MUST be on the signature kwargs.
        assert current_app.signature.call_args.kwargs.get("headers") == fairness_headers

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_unserialisable_result_raises_loudly(self, get_redis):
        """A header task returning something json.dumps can't handle
        is a typed-boundary regression. Raise loudly so the
        execution surfaces an error rather than silently dropping the
        result."""
        redis_client = MagicMock(name="redis")
        get_redis.return_value = redis_client

        # ``complex`` is a classic JSON-unserialisable leaf — no
        # ``__json__`` / ``__str__``-with-meaning, and ``default=str``
        # isn't applied (we dropped it). A regressed
        # ``BatchExecutionResult.to_dict()`` producing such a leaf
        # would land here. The test pins that the loud-failure
        # ``try/except`` actually surfaces the regression rather than
        # being a no-op.
        with pytest.raises((TypeError, ValueError)):
            barrier_decr_and_check.run(
                {"bad": complex(1, 2)},
                execution_id="exec-1",
                callback_descriptor={
                    "task_name": "cb",
                    "kwargs": {"execution_id": "exec-1"},
                    "queue": "q",
                    "fairness_headers": None,
                },
            )

    def test_link_task_is_registered_with_celery_under_canonical_name(self):
        """The link task must be importable + registered under
        ``barrier_decr_and_check`` — any worker that processes the
        link task's queue needs the name to resolve.

        Mixed-version rolling deploys depend on this: a worker
        running 6b-old code without the link task registered would
        fail with ``KeyError`` on the link's task name, which is a
        loud failure (no silent drop)."""
        assert barrier_decr_and_check.name == "barrier_decr_and_check"

    def test_link_max_retries_zero_prevents_double_decrement(self):
        """The link task MUST have ``max_retries=0``. The Lua script
        is atomic at the Redis level but the link itself is not
        idempotent: a Celery retry would replay the script and
        double-RPUSH + double-DECR, corrupting the aggregation
        (counter hits 0 prematurely; results list has duplicates).
        TTL-driven cleanup is the safety net for transient failures
        rather than Celery autoretry."""
        # Celery exposes ``max_retries`` on the task class.
        assert barrier_decr_and_check.max_retries == 0

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_negative_remaining_does_not_fire_callback(self, get_redis):
        """The Lua script returns ``remaining < 0`` when the counter
        was TTL-expired or already cleaned up. The Python side must
        NOT fire the callback in that branch — otherwise every
        subsequent task completion after a TTL expiry would dispatch
        a spurious callback."""
        redis_client = MagicMock(name="redis")
        # Lua returns ``[-1, []]`` — the ``< 0`` branch where keys
        # were already DEL'd (or never existed).
        script = MagicMock(name="script", return_value=[-1, []])
        redis_client.register_script.return_value = script
        get_redis.return_value = redis_client

        with patch("celery.current_app") as current_app:
            result = barrier_decr_and_check.run(
                {"x": 1},
                execution_id="exec-1",
                callback_descriptor={
                    "task_name": "cb",
                    "kwargs": {"execution_id": "exec-1"},
                    "queue": "q",
                    "fairness_headers": None,
                },
            )

        # No callback dispatch — the abandoned branch fires.
        current_app.signature.assert_not_called()
        assert result["status"] == "abandoned"
        assert result["remaining"] == -1


# --- TTL env validation ---


class TestTtlEnvValidation:
    """Misconfigured ``WORKER_BARRIER_KEY_TTL_SECONDS`` must raise.

    Matches the posture of ``get_barrier()`` on a typo'd
    ``WORKER_BARRIER_BACKEND``: a misconfigured TTL shorter than
    execution wall-clock is a correctness issue (spurious callback
    fires per the Lua ``< 0`` branch), so operators get a loud
    on-startup signal rather than silent degradation.
    """

    def test_non_integer_raises(self, barrier, redis_mock, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "not-an-int")
        with pytest.raises(ValueError, match=r"not an integer"):
            barrier.enqueue(
                [MagicMock()],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )

    def test_zero_raises(self, barrier, redis_mock, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "0")
        with pytest.raises(ValueError, match=r"positive integer"):
            barrier.enqueue(
                [MagicMock()],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )

    def test_negative_raises(self, barrier, redis_mock, monkeypatch):
        monkeypatch.setenv("WORKER_BARRIER_KEY_TTL_SECONDS", "-1")
        with pytest.raises(ValueError, match=r"positive integer"):
            barrier.enqueue(
                [MagicMock()],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )


# --- Mid-loop dispatch failure ---


class TestDispatchFailureCleanup:
    """If ``apply_async`` raises mid-fan-out, partially-dispatched
    tasks' links would otherwise corrupt the counter and the orphan
    state would leak. The barrier must DEL its keys before re-raising
    so the in-flight links' DECR returns negative → Lua ``< 0``
    branch cleanly abandons the execution.
    """

    def test_mid_loop_dispatch_failure_cleans_up_keys(
        self, barrier, redis_mock
    ):
        """Task K of N raises during ``apply_async`` — barrier must
        DEL both keys before propagating the exception."""
        h1 = MagicMock(name="h1")
        h2 = MagicMock(name="h2")
        h3_failing = MagicMock(name="h3_failing")
        h3_failing.clone.return_value.apply_async.side_effect = (
            RuntimeError("broker outage")
        )

        with pytest.raises(RuntimeError, match=r"broker outage"):
            barrier.enqueue(
                [h1, h2, h3_failing],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
            )

        # Initial SET + EXPIRE happened, then DEL on cleanup.
        # The DEL call should reference BOTH barrier keys.
        delete_calls = redis_mock.delete.call_args_list
        # At least one of the DEL calls must include both barrier keys
        # (the cleanup call), distinguishable from the initial
        # ``delete(_results_key(...))`` stale-list clear.
        cleanup_args = [
            set(call.args) for call in delete_calls
            if len(call.args) == 2
        ]
        assert any(
            {_remaining_key("exec-1"), _results_key("exec-1")} == args
            for args in cleanup_args
        ), (
            f"Expected DEL(remaining, results) in cleanup; saw "
            f"delete calls: {[call.args for call in delete_calls]}"
        )


# --- link_error: barrier_abort ---


class TestBarrierAbortLinkError:
    """``link_error`` propagates header-task failures.

    Without this, a failed header task would leave the counter stuck
    above 0 and the execution would hang until TTL. ``barrier_abort``
    DELs the barrier keys + logs the error; the outer task's error
    handler is responsible for the workflow status update.
    """

    def test_abort_registered_under_canonical_name(self):
        """Mixed-version rolling deploys require the link_error task
        to be importable by name on every worker that processes it."""
        from queue_backend import barrier_abort

        assert barrier_abort.name == "barrier_abort"

    def test_link_error_attached_to_each_header_task(self, barrier, redis_mock):
        """Every header task must get ``barrier_abort.s(...)`` as a
        ``.link_error``. Without this, header failures don't
        propagate and the execution hangs."""
        h1 = MagicMock(name="h1")
        h2 = MagicMock(name="h2")
        barrier.enqueue(
            [h1, h2],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        h1.clone.return_value.link_error.assert_called_once()
        h2.clone.return_value.link_error.assert_called_once()

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_abort_deletes_both_barrier_keys(self, get_redis):
        """``barrier_abort`` cleans up the barrier state on header
        failure — DELs both keys. The first call to ``barrier_abort``
        for a given execution_id wins the SET NX race and proceeds
        with cleanup + log."""
        from queue_backend import barrier_abort

        redis_client = MagicMock(name="redis")
        # ``set(...nx=True)`` returns True on first SET — this abort wins.
        redis_client.set.return_value = True
        get_redis.return_value = redis_client

        barrier_abort.run(
            MagicMock(name="request"),
            RuntimeError("header task crashed"),
            "traceback string",
            execution_id="exec-42",
        )

        redis_client.delete.assert_called_once_with(
            _remaining_key("exec-42"),
            _results_key("exec-42"),
        )

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_concurrent_aborts_deduplicate(self, get_redis):
        """N concurrent header-task failures attach the same
        ``link_error`` → N ``barrier_abort`` executions for one
        logical execution failure. Without dedup that would produce
        N ``logger.error`` calls and N Sentry events. The SET NX
        lock makes the first abort win; subsequent aborts early-exit
        silently."""
        from queue_backend import barrier_abort

        redis_client = MagicMock(name="redis")
        # First call: SET NX returns True (first abort wins).
        # Second call: SET NX returns False (lock already exists).
        redis_client.set.side_effect = [True, False]
        get_redis.return_value = redis_client

        result_1 = barrier_abort.run(
            MagicMock(name="request"),
            RuntimeError("header task 1 crashed"),
            "traceback string",
            execution_id="exec-42",
        )
        result_2 = barrier_abort.run(
            MagicMock(name="request"),
            RuntimeError("header task 2 crashed"),
            "traceback string",
            execution_id="exec-42",
        )

        # First abort completed cleanup; second deduplicated.
        assert result_1["status"] == "aborted"
        assert result_2["status"] == "deduplicated"

        # DELETE called exactly ONCE — only the winning abort cleans
        # up. The deduplicated path early-exits before DELETE.
        redis_client.delete.assert_called_once_with(
            _remaining_key("exec-42"),
            _results_key("exec-42"),
        )

    @patch("queue_backend.redis_barrier._get_redis_client")
    def test_abort_uses_setnx_with_ttl(self, get_redis):
        """The SET NX lock has an EX (TTL) — the lock key auto-
        cleans alongside the barrier keys instead of leaking
        forever on a failed execution."""
        from queue_backend import barrier_abort
        from queue_backend.redis_barrier import _KEY_TTL_DEFAULT_SECONDS

        redis_client = MagicMock(name="redis")
        redis_client.set.return_value = True
        get_redis.return_value = redis_client

        barrier_abort.run(
            MagicMock(name="request"),
            RuntimeError("crash"),
            "traceback",
            execution_id="exec-1",
        )

        # SET called with nx=True + ex=<ttl>.
        redis_client.set.assert_called_once()
        call = redis_client.set.call_args
        assert call.args[0] == "barrier:abort_lock:exec-1"
        assert call.kwargs.get("nx") is True
        assert call.kwargs.get("ex") == _KEY_TTL_DEFAULT_SECONDS


# --- Retry with reused execution_id: stale abort_lock cleanup ---


class TestAbortLockRetryCleanup:
    """A retry that reuses ``execution_id`` must not be poisoned by a
    stale ``abort_lock`` left behind by the previous failed run.

    Failure mode without the fix: execution A fails → ``barrier_abort``
    writes ``abort_lock:foo`` (TTL 6h) → within 6h, execution B retries
    with ``exec_id=foo`` → ``enqueue`` resets remaining/results but
    abort_lock survives → if any header in B fails, its ``barrier_abort``
    hits the stale lock and early-exits without DELing B's keys →
    in-flight successful tasks DECR ``remaining`` to 0 → callback fires
    with partial results → failed retry silently masked as successful.

    Fix: ``enqueue`` DELs the abort_lock alongside the results list at
    setup time, so a retry starts with a clean slate.
    """

    def test_enqueue_clears_stale_abort_lock(self, barrier, redis_mock):
        """``enqueue`` must DEL the abort_lock key at setup so a
        stale lock from a previous (failed) execution with the same
        execution_id doesn't poison the retry's abort path."""
        from queue_backend.redis_barrier import _abort_lock_key

        barrier.enqueue(
            [MagicMock(name="h1")],
            callback_task_name="cb",
            callback_kwargs={"execution_id": "exec-foo"},
            callback_queue="q",
            app_instance=MagicMock(),
        )
        # The setup DEL must include the abort_lock key (alongside
        # results) — otherwise a stale lock from a prior run with the
        # same execution_id survives into this enqueue.
        redis_mock.delete.assert_called_once_with(
            _results_key("exec-foo"),
            _abort_lock_key("exec-foo"),
        )


# --- Process-local Redis client caching ---


class TestRedisClientSingleton:
    """``_get_redis_client()`` returns a process-cached client so the
    high-frequency ``barrier_decr_and_check`` / ``barrier_abort``
    invocations reuse the same ``ConnectionPool`` rather than spinning
    up a fresh pool (and TCP handshakes) per task. At 1000-task
    fan-out the difference is 1000 vs 1 pool initialisation.
    """

    def test_get_redis_client_returns_same_instance(self):
        """Repeated calls within one process must return the same
        ``Redis`` instance — guarantees connection-pool reuse."""
        from queue_backend import redis_barrier

        # Reset the cache so this test exercises the lazy-init path.
        redis_barrier._redis_client_singleton = None
        try:
            with patch(
                "queue_backend.redis_barrier.create_redis_client"
            ) as factory:
                factory.return_value = MagicMock(name="redis_client")
                client_a = redis_barrier._get_redis_client()
                client_b = redis_barrier._get_redis_client()
                client_c = redis_barrier._get_redis_client()

            # All three calls return the same object.
            assert client_a is client_b is client_c
            # ``create_redis_client`` factory called exactly ONCE —
            # subsequent calls hit the cache.
            assert factory.call_count == 1
        finally:
            # Reset for downstream tests.
            redis_barrier._redis_client_singleton = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
