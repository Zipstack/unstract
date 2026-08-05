"""Unit tests for the backend PG-queue producer (orchestrator dispatch).

DB-free: ``PgQueueMessage`` is mocked, so these pin the wire-shape contract and
the JSON-coercion logic without needing a test database.
"""

import datetime
import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone as django_timezone

from pg_queue import producer
from unstract.core.data_models import QueueMessageState

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

    @pytest.mark.parametrize(
        "bad", [float("nan"), float("inf"), float("-inf")], ids=["nan", "inf", "-inf"]
    )
    @pytest.mark.parametrize("slot", ["args", "kwargs", "fairness"])
    def test_json_safe_rejects_non_finite_floats(self, bad, slot, caplog):
        # A non-finite float slips past the default lenient encoder and only fails at
        # the jsonb insert (DataError); allow_nan=False surfaces it as a ValueError at
        # the enqueue seam so the notification dispatcher can dead-letter it.
        #
        # Every _json_safe-coerced slot is covered, not just kwargs: the scenario this
        # guard exists for is a webhook BODY carrying a non-finite float, and
        # notification_dispatch puts the body in args[1]. inf/-inf are rejected by
        # allow_nan=False exactly like nan.
        payloads = {
            "args": {"args": ["url", {"score": bad}]},
            "kwargs": {"kwargs": {"score": bad}},
            "fairness": {"fairness": {"org_id": "o", "weight": bad}},
        }
        with patch(_MODEL) as model:
            with caplog.at_level(logging.ERROR, logger=producer.logger.name):
                with pytest.raises(ValueError):
                    producer.enqueue_task(
                        task_name="send_webhook_notification",
                        queue="notifications",
                        org_id="org-1",
                        **payloads[slot],
                    )
        model.objects.create.assert_not_called()  # never reaches the DB insert
        # The breadcrumb is the point of moving coercion inside the try — assert the
        # rendered record actually carries it, not merely that .exception() was hit.
        assert "send_webhook_notification" in caplog.text
        assert "notifications" in caplog.text
        assert "org-1" in caplog.text

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


class TestDelayedVisibility:
    """UN-3843 — ``countdown``/``eta`` defer delivery via ``scheduled`` + ``available_at``.

    A deferred row is written ``state='scheduled'`` so it is absent from the claim's
    partial index; the reaper promotes it when due. These pin the producer half of
    that contract — that the right ``(available_at, state)`` pair reaches the row, and
    that every non-deferred call still writes exactly what it wrote before this
    parameter existed.
    """

    @staticmethod
    def _create_kwargs(model):
        return model.objects.create.call_args.kwargs

    def test_no_delay_is_unchanged_and_ready(self):
        # The zero-regression case: every pre-existing call site lands here.
        before = django_timezone.now()
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="q")
        kw = self._create_kwargs(model)
        assert kw["state"] == QueueMessageState.READY.value
        assert before <= kw["available_at"] <= django_timezone.now()

    def test_countdown_defers_and_marks_scheduled(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            before = django_timezone.now()
            producer.enqueue_task(task_name="t", queue="q", countdown=90)
        kw = self._create_kwargs(model)
        assert kw["state"] == QueueMessageState.SCHEDULED.value
        # ~90s out; generous window so a slow CI box can't flake it.
        delta = (kw["available_at"] - before).total_seconds()
        assert 89 <= delta <= 95

    def test_eta_defers_and_marks_scheduled(self):
        eta = django_timezone.now() + datetime.timedelta(minutes=5)
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="q", eta=eta)
        kw = self._create_kwargs(model)
        assert kw["state"] == QueueMessageState.SCHEDULED.value
        assert kw["available_at"] == eta

    def test_naive_eta_is_read_as_utc(self):
        # USE_TZ makes `now()` aware; a naive eta would raise on comparison. Treat
        # it as UTC rather than rejecting an otherwise valid call.
        naive = (
            django_timezone.now() + datetime.timedelta(hours=1)
        ).replace(tzinfo=None)
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="q", eta=naive)
        kw = self._create_kwargs(model)
        assert kw["state"] == QueueMessageState.SCHEDULED.value
        assert kw["available_at"].tzinfo is not None

    @pytest.mark.parametrize("countdown", [0, -5])
    def test_non_positive_countdown_stays_on_the_immediate_path(self, countdown):
        # A stagger computes `i * delay`; step 0 must not pay a reaper tick just to
        # become claimable.
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="q", countdown=countdown)
        assert self._create_kwargs(model)["state"] == QueueMessageState.READY.value

    def test_past_eta_stays_on_the_immediate_path(self):
        past = django_timezone.now() - datetime.timedelta(minutes=1)
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            producer.enqueue_task(task_name="t", queue="q", eta=past)
        assert self._create_kwargs(model)["state"] == QueueMessageState.READY.value

    def test_countdown_and_eta_together_are_rejected(self):
        with patch(_MODEL) as model:
            model.objects.create.return_value = MagicMock(msg_id=1)
            with pytest.raises(ValueError, match="mutually exclusive"):
                producer.enqueue_task(
                    task_name="t",
                    queue="q",
                    countdown=10,
                    eta=django_timezone.now(),
                )
            # Rejected before any row is written — no half-enqueued message.
            model.objects.create.assert_not_called()
