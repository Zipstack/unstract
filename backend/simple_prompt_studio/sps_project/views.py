import logging

from rest_framework import viewsets
from typing import Any

from .models import SPSProject
from simple_prompt_studio.sps_prompt.models import SPSPrompt
from .serializers import SPSProjectSerializer
from django.http import HttpRequest
from rest_framework.response import Response
from prompt_studio.prompt_studio_core.serializers import (
    PromptStudioIndexSerializerSps,
    PromptStudioRunSerializerSps,
)
from prompt_studio.prompt_studio_core.constants import (
    ToolStudioPromptKeys,
)
from rest_framework.decorators import action
from simple_prompt_studio.sps_document.models import SPSDocument
from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from rest_framework import status, viewsets
from prompt_studio.prompt_studio_core.exceptions import (
    IndexingAPIError,
)
from simple_prompt_studio.sps_prompt_output.helper import SPSPromptOutputHelper

logger = logging.getLogger(__name__)

class SPSProjectView(viewsets.ModelViewSet):
    queryset = SPSProject.objects.all()
    serializer_class = SPSProjectSerializer

    @action(detail=True, methods=["post"])
    def index_document_sps(self, request: HttpRequest) -> Response:
        serializer = PromptStudioIndexSerializerSps(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool_id: str = serializer.validated_data.get("sps_id")
        document_id: str = serializer.validated_data.get(
            ToolStudioPromptKeys.DOCUMENT_ID
        )
        document: SPSDocument = SPSDocument.objects.get(pk=document_id)
        file_name: str = document.document_name
        unique_id = PromptStudioHelper.index_document_sps(
            tool_id=str(tool_id),
            file_name=file_name,
        )

        if unique_id:
            document.index_status = "success"
            document.save()
            return Response(
                {"message": "Document indexed successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            document.index_status = "failed"
            document.save()
            logger.error("Error occured while indexing. Unique ID is not valid.")
            raise IndexingAPIError()
        
    @action(detail=True, methods=["post"])
    def fetch_response_sps(self, request: HttpRequest) -> Response:
        try:
            serializer = PromptStudioRunSerializerSps(data=request.data)
            serializer.is_valid(raise_exception=True)
            tool_id: str = serializer.validated_data.get("sps_id")
            prompt_id: str = serializer.validated_data.get(
                "id"
            )
            prompt: SPSPrompt = SPSPrompt.objects.get(pk=prompt_id)
            document_id: str = serializer.validated_data.get(
                ToolStudioPromptKeys.DOCUMENT_ID
            )
            document: SPSDocument = SPSDocument.objects.get(pk=document_id)

            response: dict[str, Any] = PromptStudioHelper.prompt_responder_sps(
                tool_id=tool_id,
                file_name=document.document_name,
                prompt=prompt
            )

            output = response["output"][prompt.prompt_key]
            SPSPromptOutputHelper.handle_prompt_output_update(prompt=prompt, output=output, document_manager=document)
            return Response(response, status=status.HTTP_200_OK)
        except Exception as e:
            raise e

