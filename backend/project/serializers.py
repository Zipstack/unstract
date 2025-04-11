from typing import Any

from workflow_manager.workflow.constants import WorkflowKey
from workflow_manager.workflow.serializers import WorkflowSerializer

from backend.serializers import AuditSerializer
from project.models import Project


class ProjectSerializer(AuditSerializer):
    class Meta:
        model = Project
        fields = "__all__"

    def to_representation(self, instance: Project) -> dict[str, Any]:
        representation: dict[str, str] = super().to_representation(instance)
        wf = instance.project_workflow.first()
        representation[WorkflowKey.WF_ID] = wf.id if wf else ""
        return representation

    def create(self, validated_data: dict[str, Any]) -> Any:
        project: Project = super().create(validated_data)
        workflow_data = {"project": project.id}
        workflow_serializer = WorkflowSerializer(data=workflow_data, context=self.context)
        workflow_serializer.is_valid(raise_exception=True)
        workflow_serializer.save()
        return project
