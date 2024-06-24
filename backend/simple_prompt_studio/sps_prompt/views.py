from rest_framework import viewsets
from .serializers import SPSPromptSerializer
from .models import SPSPrompt

class SPSPromptView(viewsets.ModelViewSet):
    queryset = SPSPrompt.objects.all()
    serializer_class = SPSPromptSerializer
