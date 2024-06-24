from .models import SPSPrompt
from rest_framework import serializers

class SPSPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPSPrompt
        fields = "__all__"