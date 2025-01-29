from api_v2.models import APIDeployment
from pipeline_v2.models import Pipeline
from rest_framework import serializers
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution


class ExecutionSerializer(serializers.ModelSerializer):
    workflow_name = serializers.SerializerMethodField()
    pipeline_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowExecution
        fields = "__all__"

    def get_workflow_name(self, obj):
        """Fetch the workflow name using workflow_id"""
        # TODO: Update after making Workflow a foreign key
        # return obj.workflow.workflow_name if obj.workflow_id else None
        if workflow := Workflow.objects.filter(id=obj.workflow_id).first():
            return workflow.workflow_name
        return None

    def get_pipeline_name(self, obj):
        """Fetch the pipeline or API deployment name"""
        if not obj.pipeline_id:
            return None

        # Check if pipeline_id exists in Pipeline model
        pipeline = Pipeline.objects.filter(id=obj.pipeline_id).first()
        if pipeline:
            return pipeline.pipeline_name

        # If not found in Pipeline, check APIDeployment model
        api_deployment = APIDeployment.objects.filter(id=obj.pipeline_id).first()
        if api_deployment:
            return api_deployment.display_name

        return None
