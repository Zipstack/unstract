"""User-facing execution lists do not carry the starter's log channel.

``WorkflowExecutionSerializer`` backs the workflow, pipeline and tag execution
lists, which org admins and anyone a workflow is shared with can read. A UI
run's ``execution_log_id`` is its starter's live-log channel: it routes only
their events, so it is no business of the other readers. Workers read it from
the internal serializer, which keeps it.
"""

from django.test import SimpleTestCase

from workflow_manager.internal_serializers import (
    WorkflowExecutionSerializer as InternalWorkflowExecutionSerializer,
)
from workflow_manager.workflow_v2.serializers import WorkflowExecutionSerializer


class ExecutionSerializerLogChannelTest(SimpleTestCase):
    def test_user_facing_serializer_omits_the_log_channel(self) -> None:
        fields = WorkflowExecutionSerializer().fields

        self.assertNotIn("execution_log_id", fields)
        # Still a full view of the execution otherwise.
        for name in ("id", "workflow", "pipeline_id", "status", "created_at"):
            self.assertIn(name, fields)

    def test_internal_serializer_keeps_it_for_the_workers(self) -> None:
        # Workers set LOG_EVENTS_ID from it to stream the run's logs.
        self.assertIn("execution_log_id", InternalWorkflowExecutionSerializer().fields)
