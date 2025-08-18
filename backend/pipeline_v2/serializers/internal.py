from api_v2.models import APIDeployment
from pipeline_v2.models import Pipeline
from rest_framework import serializers


class PipelineSerializer(serializers.ModelSerializer):
    # Add computed fields for callback worker
    is_api = serializers.SerializerMethodField()
    resolved_pipeline_type = serializers.SerializerMethodField()
    resolved_pipeline_name = serializers.SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = "__all__"

    def get_is_api(self, obj):
        """Returns False for Pipeline model entries."""
        return False

    def get_resolved_pipeline_type(self, obj):
        """Returns the pipeline type from the Pipeline model."""
        return obj.pipeline_type

    def get_resolved_pipeline_name(self, obj):
        """Returns the pipeline name from the Pipeline model."""
        return obj.pipeline_name


class APIDeploymentSerializer(serializers.ModelSerializer):
    # Add computed fields for callback worker
    is_api = serializers.SerializerMethodField()
    resolved_pipeline_type = serializers.SerializerMethodField()
    resolved_pipeline_name = serializers.SerializerMethodField()

    class Meta:
        model = APIDeployment
        fields = "__all__"

    def get_is_api(self, obj):
        """Returns True for APIDeployment model entries."""
        return True

    def get_resolved_pipeline_type(self, obj):
        """Returns 'API' for APIDeployment model entries."""
        return "API"

    def get_resolved_pipeline_name(self, obj):
        """Returns the api_name from the APIDeployment model."""
        return obj.api_name
