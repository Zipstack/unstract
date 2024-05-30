import logging

from public_shares.share_controller.helpers.prompt_studio_share_helper import (
    PromptShareHelper,
)
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@permission_classes(
    [
        AllowAny,
    ]
)
@authentication_classes([])
@api_view(
    [
        "GET",
    ]
)
def prompt_metadata(request: Request) -> Response:
    share_id = request.GET.get("id")
    tool = PromptShareHelper.get_custom_tool_metadata(share_id)
    return Response(data=tool)
