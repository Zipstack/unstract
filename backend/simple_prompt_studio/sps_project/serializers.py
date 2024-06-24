from .models import SPSProject
from rest_framework import serializers
from simple_prompt_studio.sps_document.serializers import SPSDocumentSerializer
from simple_prompt_studio.sps_prompt.serializers import SPSPromptSerializer

class SPSProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPSProject
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['prompts'] = SPSPromptSerializer(instance.prompts.all(), many=True).data
        representation['documents'] = SPSDocumentSerializer(instance.documents.all(), many=True).data
        return representation