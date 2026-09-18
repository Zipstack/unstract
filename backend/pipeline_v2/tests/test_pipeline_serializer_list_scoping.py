"""``PipelineSerializer.get_fields`` must survive a list request.

DRF's ``many_init`` builds the child serializer with the same ``instance``
argument handed to the list serializer, so a paginated GET binds the page (a
``list``) to the child's ``self.instance`` -- never a single ``Pipeline``.
``get_fields`` used to guard its workflow-scoping merge with
``self.instance is not None``, which is true for that list too, so it called
``.workflow_id`` on a ``list`` and crashed every pipeline/ETL list request
with an ``AttributeError``. The guard now checks ``isinstance(self.instance,
Pipeline)`` instead.

The real module is imported and its collaborator patched (Django is loaded by
the rig's test env), so no database is touched and this stays in the unit
tier.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from pipeline_v2.models import Pipeline
from pipeline_v2.serializers.crud import PipelineSerializer
from workflow_manager.workflow_v2.models.workflow import Workflow

MUTABLE_WORKFLOWS_PATH = "pipeline_v2.serializers.crud.mutable_workflows_for"


class TestWorkflowFieldScopingSurvivesAList:
    """The instance-type guard in ``get_fields`` must not crash on a list."""

    def test_list_instance_does_not_crash(self) -> None:
        """A paginated list's ``self.instance`` is a ``list``, not a ``Pipeline``."""
        serializer = PipelineSerializer()
        serializer.instance = [MagicMock(spec=Pipeline)]

        with patch(MUTABLE_WORKFLOWS_PATH, return_value=Workflow.objects.none()):
            fields = serializer.get_fields()  # must not raise AttributeError

        assert "workflow" in fields

    def test_single_instance_still_scopes_to_its_own_workflow(self) -> None:
        """A detail/update request keeps the co-owner carve-out for its own workflow."""
        pipeline = MagicMock(spec=Pipeline, workflow_id=uuid.uuid4())
        serializer = PipelineSerializer()
        serializer.instance = pipeline

        with patch(MUTABLE_WORKFLOWS_PATH, return_value=Workflow.objects.none()):
            with patch.object(
                Workflow.objects, "filter", wraps=Workflow.objects.filter
            ) as mocked_filter:
                serializer.get_fields()

        mocked_filter.assert_called_once_with(pk=pipeline.workflow_id)
