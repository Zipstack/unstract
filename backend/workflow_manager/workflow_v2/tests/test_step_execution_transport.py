"""Tests for the PG guard on single-step execution (UN-3445 acceptance gate).

Single-step is the one entry path whose fan-out was never transport-gated: it
reaches the Celery chord in ``process_input_files`` directly, while the normal
path's PG fan-out lives in the general worker. With the flag on and the Celery
file_processing workers scaled to zero, those batches would never be consumed
and the execution would hang in EXECUTING with no PG reaper aware of it.

So the guard has to hold in *both* directions, and that is what these pin:
Celery must still run step execution unchanged (it is what staging and
production run today), and PG must refuse it loudly rather than dispatch into a
queue with no consumer.

DB-free: WorkflowExecution, resolve_transport and run_workflow are all mocked.
"""

from unittest.mock import MagicMock, patch

import pytest
from workflow_manager.workflow_v2.exceptions import WorkflowExecutionError
from workflow_manager.workflow_v2.models import Workflow
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

_TRANSPORT = "workflow_manager.workflow_v2.workflow_helper.resolve_transport"
_EXECUTION = "workflow_manager.workflow_v2.workflow_helper.WorkflowExecution"
_RUN = "workflow_manager.workflow_v2.workflow_helper.WorkflowHelper.run_workflow"

# The production comparison is `execution_action is ...START.value`, so the test
# must pass that exact object rather than an equal string literal.
_START = Workflow.ExecutionAction.START.value
_EXECUTION_ID = "11111111-1111-1111-1111-111111111111"


def _workflow():
    workflow = MagicMock()
    workflow.organization.organization_id = "org_acme"
    return workflow


def _patched_execution():
    """Mock WorkflowExecution, keeping DoesNotExist a real exception class.

    A bare MagicMock attribute is not catchable, so the production
    ``except WorkflowExecution.DoesNotExist`` would raise TypeError instead.
    """
    model = MagicMock()
    model.DoesNotExist = type("DoesNotExist", (Exception,), {})
    model.objects.get.return_value = MagicMock()
    return model


class TestStepExecutionTransportGuard:
    def test_pg_transport_refuses_instead_of_dispatching_to_celery(self):
        with patch(_EXECUTION, _patched_execution()), patch(
            _TRANSPORT, return_value="pg_queue"
        ), patch(_RUN) as run:
            with pytest.raises(WorkflowExecutionError, match="not supported"):
                WorkflowHelper.step_execution(
                    workflow=_workflow(),
                    execution_action=_START,
                    execution_id=_EXECUTION_ID,
                )
        # The point of the guard: nothing reaches the chord. Asserting the raise
        # alone would still pass if run_workflow had already fanned out.
        run.assert_not_called()

    def test_celery_transport_still_runs_step_execution(self):
        """Flag-off is what staging and production run — it must be untouched."""
        with patch(_EXECUTION, _patched_execution()), patch(
            _TRANSPORT, return_value="celery"
        ), patch(_RUN, return_value="ran") as run:
            result = WorkflowHelper.step_execution(
                workflow=_workflow(),
                execution_action=_START,
                execution_id=_EXECUTION_ID,
            )
        assert result == "ran"
        assert run.call_args.kwargs["single_step"] is True

    def test_transport_is_resolved_on_the_execution_id(self):
        """entity_id must be the execution id — it is what Flipt buckets on, and
        what keeps one execution from re-bucketing across transports."""
        with patch(_EXECUTION, _patched_execution()), patch(
            _TRANSPORT, return_value="celery"
        ) as resolve, patch(_RUN):
            WorkflowHelper.step_execution(
                workflow=_workflow(),
                execution_action=_START,
                execution_id=_EXECUTION_ID,
            )
        assert resolve.call_args.kwargs["execution_id"] == _EXECUTION_ID
        assert resolve.call_args.kwargs["organization_id"] == "org_acme"

    def test_no_execution_id_creates_a_step_execution_without_resolving(self):
        """The START-without-id branch only mints a row; it dispatches nothing, so
        it must not consume a Flipt evaluation (and must not be blocked)."""
        with patch(_TRANSPORT) as resolve, patch.object(
            WorkflowHelper, "create_and_make_execution_response", return_value="created"
        ):
            result = WorkflowHelper.step_execution(
                workflow=_workflow(), execution_action=_START, execution_id=None
            )
        assert result == "created"
        resolve.assert_not_called()

    def test_missing_execution_falls_back_to_creating_one(self):
        """Pre-existing behaviour: a stale execution_id re-mints rather than 404s.
        Pinned so the guard's placement inside the try/except cannot change it."""
        model = _patched_execution()
        model.objects.get.side_effect = model.DoesNotExist
        with patch(_EXECUTION, model), patch(_TRANSPORT) as resolve, patch.object(
            WorkflowHelper, "create_and_make_execution_response", return_value="created"
        ):
            result = WorkflowHelper.step_execution(
                workflow=_workflow(),
                execution_action=_START,
                execution_id=_EXECUTION_ID,
            )
        assert result == "created"
        resolve.assert_not_called()
