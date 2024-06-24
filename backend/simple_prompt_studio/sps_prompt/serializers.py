from rest_framework import serializers

from .models import SPSPrompt


class SPSPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPSPrompt
        fields = "__all__"
