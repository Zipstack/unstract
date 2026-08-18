"""WorkflowExecutionInternalViewSet._cascade_terminal_files (UN-3661).

When the reaper marks a stranded execution terminal with
``cascade_terminal_files``, the execution's non-terminal (PENDING/EXECUTING) file
executions must be marked to the same terminal status atomically — so a recovered
strand never leaves execution=ERROR while its files stay EXECUTING (the b11ba2f3
inconsistency). Terminal files (COMPLETED/ERROR/STOPPED) are left untouched.
"""

from django.test import TestCase

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_cascade = WorkflowExecutionInternalViewSet._cascade_terminal_files


class CascadeTerminalFilesTests(TestCase):
    def setUp(self):
        self.workflow = Workflow.objects.create(workflow_name="test-cascade-wf")
        self.execution = WorkflowExecution.objects.create(
            workflow=self.workflow, status=ExecutionStatus.EXECUTING
        )

    def _file(self, name, status):
        return WorkflowFileExecution.objects.create(
            workflow_execution=self.execution, file_name=name, status=status.value
        )

    def _reload(self, fe):
        fe.refresh_from_db()
        return fe

    def test_cascades_only_non_terminal_files_to_the_terminal_status(self):
        executing = self._file("a.pdf", ExecutionStatus.EXECUTING)
        pending = self._file("b.pdf", ExecutionStatus.PENDING)
        completed = self._file("c.pdf", ExecutionStatus.COMPLETED)

        _cascade(self.execution, ExecutionStatus.ERROR, "boom")

        assert self._reload(executing).status == ExecutionStatus.ERROR.value
        assert self._reload(pending).status == ExecutionStatus.ERROR.value
        # A file that already finished is left alone (no status overwrite).
        assert self._reload(completed).status == ExecutionStatus.COMPLETED.value
        assert self._reload(executing).execution_error == "boom"

    def test_non_terminal_target_status_is_a_noop(self):
        # The cascade only fires when the execution itself went terminal.
        executing = self._file("a.pdf", ExecutionStatus.EXECUTING)
        _cascade(self.execution, ExecutionStatus.EXECUTING, "x")
        assert self._reload(executing).status == ExecutionStatus.EXECUTING.value

    def test_idempotent_second_run_changes_nothing(self):
        executing = self._file("a.pdf", ExecutionStatus.EXECUTING)
        _cascade(self.execution, ExecutionStatus.ERROR, "first")
        assert self._reload(executing).status == ExecutionStatus.ERROR.value
        # Second run: the file is already terminal → excluded → error not clobbered.
        _cascade(self.execution, ExecutionStatus.ERROR, "second")
        assert self._reload(executing).execution_error == "first"
