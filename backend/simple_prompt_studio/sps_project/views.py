from rest_framework import viewsets
from .serializers import SPSProjectSerializer
from .models import SPSProject

class SPSProjectView(viewsets.ModelViewSet):
    queryset = SPSProject.objects.all()
    serializer_class = SPSProjectSerializer
