import logging

from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@require_http_methods(["GET"])
def health_check(request: Request) -> Response:
    logger.debug("Verifying backend health..")
    return Response(status=200)
