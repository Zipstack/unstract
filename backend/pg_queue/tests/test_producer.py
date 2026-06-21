"""Unit tests for the backend PG-queue producer (orchestrator dispatch, 9e PR A).

DB-free: ``PgQueueMessage`` is mocked, so these pin the wire-shape contract and
the JSON-coercion logic without needing a test database.
"""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest

from pg_queue import producer

_MODEL = "pg_queue.producer.PgQueueMessage"


class TestEnqueueTask:
    def test_builds_taskpayload_row(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=4242)
            msg_id = producer.enqueue_task(
                task_name="async_execute_bin",
                queue="celery_api_deployments",
                args=["org", "wf", "exec"],
                kwargs={"transport": "pg_queue"},
                org_id="org",
                priority=5,
                fairness={
                    "org_id": "org",
                    "workload_type": "api",
                    "pipeline_priority": 5,
                },
            )
        assert msg_id == 4242
        kw = model.objects.create.call_args.kwargs
        assert kw["queue_name"] == "celery_api_deployments"
        assert kw["org_id"] == "org"
        assert kw["priority"] == 5
        msg = kw["message"]
        assert msg["task_name"] == "async_execute_bin"
        assert msg["queue"] == "celery_api_deployments"
        assert msg["args"] == ["org", "wf", "exec"]
        assert msg["kwargs"] == {"transport": "pg_queue"}
        assert msg["fairness"]["workload_type"] == "api"

    def test_uuid_args_kwargs_are_json_coerced(self):
        """PgQueueMessage.message is a plain JSONField → UUIDs in args/kwargs must
        be coerced to str (the worker consumer receives string ids)."""
        wf = uuid.UUID("ebed2834-c9fb-4b6c-8df3-9dd841f616bb")
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(
                task_name="async_execute_bin",
                queue="celery",
                args=[wf],
                kwargs={"pipeline_id": wf},
            )
        msg = model.objects.create.call_args.kwargs["message"]
        assert msg["args"] == [str(wf)]
        assert msg["kwargs"] == {"pipeline_id": str(wf)}
        assert all(isinstance(a, str) for a in msg["args"])

    def test_none_queue_defaults_to_general(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="async_execute_bin", queue=None)
        kw = model.objects.create.call_args.kwargs
        assert kw["queue_name"] == producer.DEFAULT_GENERAL_QUEUE == "celery"
        assert kw["message"]["queue"] == "celery"

    def test_empty_args_kwargs_and_no_fairness(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="celery")
        msg = model.objects.create.call_args.kwargs["message"]
        assert msg["args"] == []
        assert msg["kwargs"] == {}
        assert msg["fairness"] is None

    @pytest.mark.parametrize("priority", [1, 5, 10])
    def test_priority_boundary_values_accepted(self, priority):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="celery", priority=priority)
        assert model.objects.create.call_args.kwargs["priority"] == priority

    @pytest.mark.parametrize("priority", [0, 11, -1])
    def test_priority_out_of_range_raises(self, priority):
        with pytest.raises(ValueError):
            producer.enqueue_task(task_name="t", queue="celery", priority=priority)

    def test_default_priority_when_omitted(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="celery")
        assert model.objects.create.call_args.kwargs["priority"] == 5  # FAIRNESS_DEFAULT

    def test_json_safe_coerces_datetime(self):
        dt = datetime.datetime(2026, 6, 18, 12, 0, 0)
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(
                task_name="t", queue="celery", kwargs={"when": dt}
            )
        when = model.objects.create.call_args.kwargs["message"]["kwargs"]["when"]
        assert isinstance(when, str) and "2026-06-18" in when

    def test_enqueue_failure_logs_and_propagates(self):
        with patch(_MODEL) as model:
            model.objects.create.side_effect = RuntimeError("db down")
            with pytest.raises(RuntimeError):
                producer.enqueue_task(task_name="t", queue="celery")

    def test_reply_key_and_callback_mutually_exclusive(self):
        spec = {"task_name": "cb", "kwargs": {}, "queue": "ide_callback"}
        with pytest.raises(ValueError, match="mutually exclusive"):
            producer.enqueue_task(
                task_name="execute_extraction",
                queue="celery_executor_legacy",
                reply_key="rk",
                on_success=spec,
            )

    def test_continuation_specs_are_json_coerced(self):
        # A callback's kwargs can carry a UUID/datetime → must be coerced like
        # args/kwargs, else the JSONField insert raises at dispatch (caller-visible).
        uid = uuid.UUID("ebed2834-c9fb-4b6c-8df3-9dd841f616bb")
        spec = {
            "task_name": "ide_prompt_complete",
            "kwargs": {"callback_kwargs": {"doc_id": uid}},
            "queue": "ide_callback",
        }
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(
                task_name="execute_extraction",
                queue="celery_executor_legacy",
                on_success=spec,
                task_id="t1",
            )
        msg = model.objects.create.call_args.kwargs["message"]
        assert msg["on_success"]["kwargs"]["callback_kwargs"]["doc_id"] == str(uid)
