"""Tests for the 9e transport-resolution seam.

PR 1 is the *inert* seam: ``resolve_transport`` always returns Celery, so the
whole pipeline is byte-identical to today. These tests pin that contract so a
future change (PR 3, Flipt wiring) can't silently flip the default.
"""

from unittest.mock import MagicMock

from unstract.core.data_models import (
    DEFAULT_WORKFLOW_TRANSPORT,
    WorkflowTransport,
    normalize_transport,
)
from workflow_manager.workflow_v2.transport import resolve_transport


class TestWorkflowTransportEnum:
    def test_values(self):
        assert WorkflowTransport.CELERY.value == "celery"
        assert WorkflowTransport.PG_QUEUE.value == "pg_queue"

    def test_default_is_celery(self):
        assert DEFAULT_WORKFLOW_TRANSPORT == WorkflowTransport.CELERY.value


class TestResolveTransport:
    def test_resolves_celery_by_default(self):
        """PR 1: always Celery, regardless of inputs."""
        assert resolve_transport(workflow_id="wf-1") == WorkflowTransport.CELERY.value

    def test_accepts_optional_args_without_changing_result(self):
        """The pipeline/org args are accepted now (stable signature for PR 3's
        Flipt wiring) but must not change the inert result."""
        assert (
            resolve_transport(
                workflow_id="wf-1",
                pipeline_id="pipe-1",
                organization_id="org-1",
            )
            == WorkflowTransport.CELERY.value
        )

    def test_result_is_a_valid_transport_value(self):
        valid = {t.value for t in WorkflowTransport}
        assert resolve_transport(workflow_id="wf-1") in valid


class TestNormalizeTransport:
    """The fail-closed coercion used at every untrusted read boundary."""

    def test_recognized_values_pass_through(self):
        assert normalize_transport("celery") == "celery"
        assert normalize_transport("pg_queue") == "pg_queue"

    def test_unrecognized_value_falls_back_to_celery(self):
        assert normalize_transport("celary") == DEFAULT_WORKFLOW_TRANSPORT
        assert normalize_transport("pg-queue") == DEFAULT_WORKFLOW_TRANSPORT

    def test_none_and_empty_fall_back_to_celery(self):
        assert normalize_transport(None) == DEFAULT_WORKFLOW_TRANSPORT
        assert normalize_transport("") == DEFAULT_WORKFLOW_TRANSPORT

    def test_invalid_value_logs_a_warning_when_logger_given(self):
        log = MagicMock()
        assert normalize_transport("bogus", logger=log, context=" [exec:x]") == "celery"
        log.warning.assert_called_once()

    def test_valid_value_does_not_warn(self):
        log = MagicMock()
        normalize_transport("pg_queue", logger=log)
        log.warning.assert_not_called()
