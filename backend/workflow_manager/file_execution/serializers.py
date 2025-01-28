from rest_framework import serializers

from .models import WorkflowFileExecution


class WorkflowFileExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowFileExecution
        fields = "__all__"
