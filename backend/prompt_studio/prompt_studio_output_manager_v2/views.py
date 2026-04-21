import logging
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.http import HttpRequest
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.common_utils import CommonUtils
from utils.filtering import FilterHelper

from prompt_studio.prompt_studio_output_manager_v2.constants import (
    PromptOutputManagerErrorMessage,
    PromptStudioOutputManagerKeys,
)
from prompt_studio.prompt_studio_output_manager_v2.output_manager_helper import (
    OutputManagerHelper,
)
from prompt_studio.prompt_studio_output_manager_v2.serializers import (
    PromptStudioOutputSerializer,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt

from .models import PromptStudioOutputManager

logger = logging.getLogger(__name__)


class PromptStudioOutputView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = PromptStudioOutputSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
            PromptStudioOutputManagerKeys.PROMPT_ID,
            PromptStudioOutputManagerKeys.PROFILE_MANAGER,
            PromptStudioOutputManagerKeys.DOCUMENT_MANAGER,
            PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT,
        )

        # Get the query parameter for "is_single_pass_extract"
        is_single_pass_extract_param = self.request.GET.get(
            PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT, "false"
        )

        # Convert the string representation to a boolean value
        is_single_pass_extract = CommonUtils.str_to_bool(is_single_pass_extract_param)

        filter_args[PromptStudioOutputManagerKeys.IS_SINGLE_PASS_EXTRACT] = (
            is_single_pass_extract
        )

        if filter_args:
            queryset = PromptStudioOutputManager.objects.filter(**filter_args)
        else:
            queryset = PromptStudioOutputManager.objects.all()

        return queryset

    def latest_outputs_by_keys(self, request: HttpRequest) -> Response:
        """Return the most recent raw output value per source prompt key.

        Used by the lookup Test panel's "Use Latest Outputs" button to
        pre-fill {{input.X}} fields from prior prompt runs in the linked
        tool. Always returns the raw extraction — the enriched value would
        already include lookup post-processing, which would defeat the
        purpose of testing the lookup with sample inputs.
        """
        tool_id = request.GET.get("tool_id")
        keys_param = request.GET.get("prompt_keys", "")
        if not tool_id:
            raise APIException(
                detail=PromptOutputManagerErrorMessage.TOOL_VALIDATION,
                code=400,
            )

        prompt_keys = [k.strip() for k in keys_param.split(",") if k.strip()]
        if not prompt_keys:
            return Response({}, status=status.HTTP_200_OK)

        prompt_id_to_key = dict(
            ToolStudioPrompt.objects.filter(
                tool_id=tool_id, prompt_key__in=prompt_keys
            ).values_list("prompt_id", "prompt_key")
        )
        if not prompt_id_to_key:
            return Response({}, status=status.HTTP_200_OK)

        outputs = (
            PromptStudioOutputManager.objects.filter(
                prompt_id__in=prompt_id_to_key.keys()
            )
            .exclude(output__isnull=True)
            .exclude(output__exact="")
            .order_by("-modified_at")
            .values("prompt_id", "output")
        )

        result: dict[str, str] = {}
        for row in outputs:
            key = prompt_id_to_key.get(row["prompt_id"])
            if key and key not in result:
                result[key] = row["output"]
            if len(result) == len(prompt_id_to_key):
                break

        return Response(result, status=status.HTTP_200_OK)

    def get_output_for_tool_default(self, request: HttpRequest) -> Response:
        # Get the tool_id from request parameters
        # TODO: Setup Serializer here
        tool_id = request.GET.get("tool_id")
        document_manager_id = request.GET.get("document_manager")
        tool_validation_message = PromptOutputManagerErrorMessage.TOOL_VALIDATION
        tool_not_found = PromptOutputManagerErrorMessage.TOOL_NOT_FOUND
        if not tool_id:
            raise APIException(detail=tool_validation_message, code=400)

        try:
            # Fetch ToolStudioPrompt records based on tool_id
            tool_studio_prompts = ToolStudioPrompt.objects.filter(
                tool_id=tool_id
            ).order_by("sequence_number")
        except ObjectDoesNotExist:
            raise APIException(detail=tool_not_found, code=400)

        # Invoke helper method to frame and fetch default response.
        result: dict[str, Any] = OutputManagerHelper.fetch_default_output_response(
            tool_studio_prompts=tool_studio_prompts,
            document_manager_id=document_manager_id,
            use_default_profile=True,
        )

        return Response(result, status=status.HTTP_200_OK)
