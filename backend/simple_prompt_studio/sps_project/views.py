from rest_framework import viewsets

from .models import SPSProject
from .serializers import SPSProjectSerializer


class SPSProjectView(viewsets.ModelViewSet):
    queryset = SPSProject.objects.all()
    serializer_class = SPSProjectSerializer
