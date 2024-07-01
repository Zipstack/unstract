from rest_framework import serializers

from .models import SPSPromptOutput


class SPSPromptOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = SPSPromptOutput
        fields = "__all__"
