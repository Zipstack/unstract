import logging
from typing import Any

from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from public_shares.share_controller.controllers.prompt_share_controller import (
    PromptShareController,
)
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(
    [
        "GET",
    ]
)
def prompt_metadata(request: Request) -> Response:
    share_id = request.GET.get("id")
    tool = PromptShareController.get_custom_tool_metadata(share_id)
    return Response(data=tool)


@api_view(["GET"])
def get_select_choices(request: Request) -> Response:
    """Method to return all static dropdown field values.

    The field values are retrieved from `./static/select_choices.json`.

    Returns:
        Response: Reponse of dropdown dict
    """
    try:
        select_choices: dict[str, Any] = PromptStudioHelper.get_select_fields()
        return Response(select_choices, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Error occured while fetching select fields {e}")
        return Response(select_choices, status=status.HTTP_204_NO_CONTENT)


@api_view(
    [
        "GET",
    ]
)
def document_manager(request: Request) -> Response:
    share_id = request.GET.get("id")
    document_metadata = PromptShareController.get_document_metadata(share_id)
    return Response(data=document_metadata)


@api_view(
    [
        "GET",
    ]
)
def profile_manager(request: Request) -> Response:
    share_id = request.GET.get("id")
    profile_metadata = PromptShareController.get_profile_manager_metadata(share_id)
    return Response(data=profile_metadata)


@api_view(
    [
        "GET",
    ]
)
def prompt_manager(request: Request) -> Response:
    share_id = request.GET.get("id")
    prompt_metadata = PromptShareController.get_prompt_manager_metadata(share_id)
    return Response(data=prompt_metadata)
