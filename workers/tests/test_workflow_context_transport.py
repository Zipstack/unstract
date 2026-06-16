"""Tests for the 9e transport field carried on ``WorkflowContextData``.

The transport a workflow execution rides is decided once at creation and
carried in the task payload; on the worker side it lands on the live
``WorkflowContextData`` so the fan-out (PR 2) can read it. PR 1 only adds the
field with a Celery default — these tests pin that it defaults and round-trips.
"""

from unittest.mock import MagicMock

from shared.models.execution_models import (
    WorkerOrganizationContext,
    WorkflowContextData,
)

from unstract.core.data_models import DEFAULT_WORKFLOW_TRANSPORT, WorkflowTransport


def _make_context(**overrides):
    org_context = WorkerOrganizationContext(
        organization_id="org-1",
        api_client=MagicMock(),
    )
    kwargs = dict(
        workflow_id="wf-1",
        workflow_name="wf-name",
        workflow_type="TASK",
        execution_id="exec-1",
        organization_context=org_context,
        files={},
    )
    kwargs.update(overrides)
    return WorkflowContextData(**kwargs)


class TestWorkflowContextTransport:
    def test_defaults_to_celery(self):
        """A context built without a transport rides legacy Celery."""
        assert _make_context().transport == DEFAULT_WORKFLOW_TRANSPORT
        assert _make_context().transport == WorkflowTransport.CELERY.value

    def test_carries_pg_queue_when_set(self):
        ctx = _make_context(transport=WorkflowTransport.PG_QUEUE.value)
        assert ctx.transport == "pg_queue"
