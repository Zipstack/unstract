"""Tests for the 9e transport-resolution seam.

PR 1 is the *inert* seam: ``resolve_transport`` always returns Celery, so the
whole pipeline is byte-identical to today. These tests pin that contract so a
future change (PR 3, Flipt wiring) can't silently flip the default.
"""

from unstract.core.data_models import DEFAULT_WORKFLOW_TRANSPORT, WorkflowTransport
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
