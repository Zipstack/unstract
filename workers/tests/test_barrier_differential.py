"""Differential test — both ``Barrier`` substrates produce equivalent
callback firings for a fixed input.

This is the load-bearing test that justifies the substrate swap:
given the same header tasks + callback descriptor + fairness, both
``CeleryChordBarrier`` and ``RedisDecrBarrier`` must ultimately fire
the same callback with the same ``(task_name, args, kwargs, queue,
headers)``. The execution paths diverge — chord aggregates via
Celery's chord backend, redis aggregates via ``DECR remaining`` +
``RPUSH`` — but the observable output (what the callback receives)
is equivalent.

If this test fails, the substrate swap is *not* safe to roll out:
the callback would see different aggregated results or different
metadata between substrates, breaking executions when the flag
flips.

Note this is a unit-level differential — it pins the wire shape of
the callback dispatch, not full end-to-end equivalence. A future
integration test (against real Celery + Redis with N parallel
workers) would belong in ``test_barrier_integration.py``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from queue_backend import CeleryChordBarrier, RedisDecrBarrier, barrier_decr_and_check
from queue_backend.fairness import FairnessKey, WorkloadType


# A fixed scenario both substrates run through.
_HEADER_TASK_RESULTS = [
    {"batch_id": "b1", "files": ["f1", "f2"], "status": "ok"},
    {"batch_id": "b2", "files": ["f3", "f4"], "status": "ok"},
    {"batch_id": "b3", "files": ["f5"], "status": "ok"},
]
_CALLBACK_TASK = "process_batch_callback_api"
_CALLBACK_KWARGS = {
    "execution_id": "exec-differential-1",
    "pipeline_id": "pipe-x",
    "organization_id": "org-y",
}
_CALLBACK_QUEUE = "api_file_processing_callback"
_FAIRNESS = FairnessKey(org_id="org-y", workload_type=WorkloadType.API)


def _capture_chord_callback_dispatch() -> dict:
    """Run ``CeleryChordBarrier.enqueue`` against a mocked ``chord``
    and return the callback signature's construction args.

    Chord's wire model: ``chord(header_tasks)(callback_signature)`` —
    the callback_signature is built via ``app.signature(name, kwargs=...,
    queue=..., headers=...)`` and then passed as the body.
    """
    app = MagicMock(name="app")
    headers_captured = {}

    def signature_recorder(name, **kwargs):
        headers_captured["task_name"] = name
        headers_captured["args"] = kwargs.get("args")  # None for chord callback
        headers_captured["kwargs"] = kwargs.get("kwargs")
        headers_captured["queue"] = kwargs.get("queue")
        headers_captured["headers"] = kwargs.get("headers")
        return MagicMock(name="callback_signature")

    app.signature.side_effect = signature_recorder
    header = [MagicMock(name=f"h{i}") for i in range(len(_HEADER_TASK_RESULTS))]

    with patch("queue_backend.barrier.chord"):
        CeleryChordBarrier().enqueue(
            header,
            callback_task_name=_CALLBACK_TASK,
            callback_kwargs=_CALLBACK_KWARGS,
            callback_queue=_CALLBACK_QUEUE,
            app_instance=app,
            fairness=_FAIRNESS,
        )
    return headers_captured


def _capture_redis_callback_dispatch() -> dict:
    """Drive ``RedisDecrBarrier.enqueue`` + simulate the link task
    completing for all header tasks, then capture the final
    callback signature's construction args at the post-aggregation
    dispatch site.
    """
    redis_mock = MagicMock(name="redis")
    barrier = RedisDecrBarrier(redis_client=redis_mock)
    header = [MagicMock(name=f"h{i}") for i in range(len(_HEADER_TASK_RESULTS))]
    barrier.enqueue(
        header,
        callback_task_name=_CALLBACK_TASK,
        callback_kwargs=_CALLBACK_KWARGS,
        callback_queue=_CALLBACK_QUEUE,
        app_instance=MagicMock(name="app"),
        fairness=_FAIRNESS,
    )

    # Now simulate each link firing. The first N-1 see remaining > 0;
    # the last sees remaining == 0 and dispatches the callback.
    headers_captured = {}

    def signature_recorder(name, **kwargs):
        headers_captured["task_name"] = name
        headers_captured["args"] = kwargs.get("args")
        headers_captured["kwargs"] = kwargs.get("kwargs")
        headers_captured["queue"] = kwargs.get("queue")
        headers_captured["headers"] = kwargs.get("headers")
        cb_sig = MagicMock(name="callback_signature")
        cb_sig.apply_async.return_value = MagicMock(id="callback-task-id")
        return cb_sig

    # Simulate the Lua script's return for each link invocation.
    # First N-1 calls: [remaining, []]. Last call: [0, [serialised results]].
    n = len(_HEADER_TASK_RESULTS)
    serialised_results = [json.dumps(r) for r in _HEADER_TASK_RESULTS]
    return_values = [
        [n - 1 - i, []] for i in range(n - 1)
    ] + [[0, serialised_results]]
    script_mock = MagicMock(side_effect=return_values)

    with patch("queue_backend.redis_barrier._get_redis_client") as get_redis:
        # Inside the link task, ``_get_redis_client()`` is called to
        # build the script invocation. Return a mock whose
        # register_script returns the script_mock that yields the
        # sequenced return values.
        link_redis = MagicMock(name="link_redis")
        link_redis.register_script.return_value = script_mock
        get_redis.return_value = link_redis

        with patch("celery.current_app") as current_app:
            current_app.signature.side_effect = signature_recorder
            for header_result in _HEADER_TASK_RESULTS:
                barrier_decr_and_check.run(
                    header_result,
                    execution_id=_CALLBACK_KWARGS["execution_id"],
                    callback_descriptor={
                        "task_name": _CALLBACK_TASK,
                        "kwargs": _CALLBACK_KWARGS,
                        "queue": _CALLBACK_QUEUE,
                        "fairness_headers": _FAIRNESS.as_header(),
                    },
                )
    return headers_captured


class TestBarrierSubstrateDifferential:
    """Both substrates must produce equivalent callback firings.

    A failure here means the swap is not safe — flag flipping in
    Phase 6c would change the data the callback receives.
    """

    def test_same_callback_task_name(self):
        """Both substrates fire the same callback task name."""
        chord_cap = _capture_chord_callback_dispatch()
        redis_cap = _capture_redis_callback_dispatch()
        assert chord_cap["task_name"] == redis_cap["task_name"] == _CALLBACK_TASK

    def test_same_callback_kwargs(self):
        """Both substrates forward the same ``execution_id`` /
        ``pipeline_id`` / ``organization_id`` to the callback."""
        chord_cap = _capture_chord_callback_dispatch()
        redis_cap = _capture_redis_callback_dispatch()
        assert chord_cap["kwargs"] == redis_cap["kwargs"] == _CALLBACK_KWARGS

    def test_same_callback_queue(self):
        """Both substrates route the callback to the same queue —
        without this, post-Phase-6c the callback could land on a
        worker that doesn't have it registered."""
        chord_cap = _capture_chord_callback_dispatch()
        redis_cap = _capture_redis_callback_dispatch()
        assert chord_cap["queue"] == redis_cap["queue"] == _CALLBACK_QUEUE

    def test_same_fairness_headers(self):
        """Both substrates ride the same ``x-fairness-key`` AMQP
        header on the callback. Mismatch would mean post-flag-flip
        executions route through different fairness slots, which
        the L1/L2/L3 admission logic could throttle differently."""
        chord_cap = _capture_chord_callback_dispatch()
        redis_cap = _capture_redis_callback_dispatch()
        assert chord_cap["headers"] == redis_cap["headers"] == _FAIRNESS.as_header()

    def test_redis_substrate_passes_aggregated_results_as_first_arg(self):
        """Chord's callback receives ``[result_1, result_2, ...]`` via
        Celery's chord-aggregator (an implicit first positional arg
        Celery injects). The Redis substrate must replicate the
        same shape — pass the aggregated list explicitly via
        ``args=[all_results]`` on the callback signature.

        We can't observe chord's implicit arg injection from the
        outside (it's the chord backend's job), but we CAN pin the
        Redis substrate's behaviour: when aggregation completes,
        the callback signature's ``args[0]`` MUST equal the
        original header-task results list. That's the contract the
        callback already depends on (``file_batch_results: list[dict]``
        — see callback/tasks.py:1552)."""
        redis_cap = _capture_redis_callback_dispatch()
        assert redis_cap["args"] == [_HEADER_TASK_RESULTS], (
            f"Redis substrate's callback args must be a list "
            f"containing one list-of-results (matching chord's "
            f"aggregator shape). Got: {redis_cap['args']!r}"
        )

    def test_both_handle_empty_headers_identically(self):
        """Empty header → ``None`` from both substrates. The caller's
        ``if result is None:`` branch then handles the zero-files
        contract uniformly."""
        chord_result = CeleryChordBarrier().enqueue(
            [],
            callback_task_name=_CALLBACK_TASK,
            callback_kwargs=_CALLBACK_KWARGS,
            callback_queue=_CALLBACK_QUEUE,
            app_instance=MagicMock(),
        )
        redis_result = RedisDecrBarrier(redis_client=MagicMock()).enqueue(
            [],
            callback_task_name=_CALLBACK_TASK,
            callback_kwargs=_CALLBACK_KWARGS,
            callback_queue=_CALLBACK_QUEUE,
            app_instance=MagicMock(),
        )
        assert chord_result is None
        assert redis_result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
