"""Tests for the single-step execution guard (UN-3445 acceptance gate, UN-4046).

Single-step is the one entry path whose fan-out was never moved onto PG: it
reaches the Celery chord in ``process_input_files`` directly, while the normal
path's PG fan-out lives in the general worker. With no Celery file_processing
workers those batches would never be consumed and the execution would hang in
EXECUTING with no PG reaper aware of it — so it refuses loudly instead.

It used to refuse only when the ``pg_queue_enabled`` flag resolved to PG. The
flag is gone (UN-4046) and PG is the only transport, so the refusal is
unconditional and the "celery still runs it" / "transport is resolved on the
execution id" cases no longer describe anything.

DB-free: WorkflowExecution and run_workflow are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest
from workflow_manager.workflow_v2.exceptions import WorkflowExecutionError
from workflow_manager.workflow_v2.models import Workflow
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

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


class TestStepExecutionGuard:
    def test_refuses_instead_of_dispatching_into_an_unconsumed_queue(self):
        with patch(_EXECUTION, _patched_execution()), patch(_RUN) as run:
            with pytest.raises(WorkflowExecutionError, match="not supported"):
                WorkflowHelper.step_execution(
                    workflow=_workflow(),
                    execution_action=_START,
                    execution_id=_EXECUTION_ID,
                )
        # The point of the guard: nothing reaches the chord. Asserting the raise
        # alone would still pass if run_workflow had already fanned out.
        run.assert_not_called()
