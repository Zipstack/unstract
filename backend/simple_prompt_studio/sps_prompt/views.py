from rest_framework import viewsets

from .models import SPSPrompt
from .serializers import SPSPromptSerializer


class SPSPromptView(viewsets.ModelViewSet):
    queryset = SPSPrompt.objects.all()
    serializer_class = SPSPromptSerializer
