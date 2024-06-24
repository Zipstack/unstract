from typing import Any

from file_management.file_management_helper import FileManagerHelper
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from simple_prompt_studio.sps_project.models import SPSProject

from unstract.connectors.filesystems.local_storage.local_storage import LocalStorageFS

from .models import SPSDocument
from .serializers import (
    SPSDocumentSerializer,
    SPSFileInfoSerializer,
    SPSFileUploadSerializer,
)


class SPSDocumentView(viewsets.ModelViewSet):
    queryset = SPSDocument.objects.all()
    serializer_class = SPSDocumentSerializer

    @action(detail=True, methods=["post"])
    def upload_documents(self, request: Request) -> Response:
        serializer = SPSFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_files: Any = serializer.validated_data.get("file")
        sps_project_id: str = serializer.validated_data.get("sps_project_id")

        file_path = FileManagerHelper.handle_sub_directory_for_sps(
            sps_project_id=sps_project_id
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        documents = []
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name

            # Create a record in the db for the file
            sps_project: SPSProject = SPSProject.objects.get(pk=sps_project_id)
            document: SPSDocument = SPSDocument.objects.create(
                tool=sps_project, document_name=file_name
            )
            # Create a dictionary to store document data
            doc = {
                "document_id": document.document_id,
                "document_name": document.document_name,
            }
            FileManagerHelper.upload_file(
                file_system,
                file_path,
                uploaded_file,
                file_name,
            )
            documents.append(doc)
        return Response({"data": documents})

    @action(detail=True, methods=["get"])
    def fetch_contents_ide(self, request: Request, pk: Any = None) -> Response:
        serializer = SPSFileInfoSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        document_id: str = serializer.validated_data.get("document_id")
        document: SPSDocument = SPSDocument.objects.get(pk=document_id)
        file_name: str = document.document_name
        view_type: str = serializer.validated_data.get("view_type")
        sps_project_id: str = serializer.validated_data.get("sps_project_id")

        filename_without_extension = file_name.rsplit(".", 1)[0]
        if view_type == "extract":
            file_name = f"{'extract'}/" f"{filename_without_extension}.txt"

        file_path = FileManagerHelper.handle_sub_directory_for_sps(
            sps_project_id=sps_project_id
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        if not file_path.endswith("/"):
            file_path += "/"
        file_path += file_name
        # Temporary Hack for frictionless onboarding as the user id will be empty
        try:
            contents = FileManagerHelper.fetch_file_contents(file_system, file_path)
        except Exception as e:
            print(e)

        return Response({"data": contents})
