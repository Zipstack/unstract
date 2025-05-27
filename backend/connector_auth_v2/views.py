import logging
import uuid

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.user_session import UserSessionUtils

from connector_auth_v2.constants import SocialAuthConstants
from connector_auth_v2.exceptions import KeyNotConfigured

logger = logging.getLogger(__name__)


class ConnectorAuthViewSet(viewsets.ViewSet):
    """Contains methods for Connector related authentication."""

    versioning_class = URLPathVersioning

    def cache_key(
        self: "ConnectorAuthViewSet", request: Request, backend: str
    ) -> Response:
        if backend == SocialAuthConstants.GOOGLE_OAUTH and (
            settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY is None
            or settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET is None
        ):
            msg = (
                f"Keys not configured for {backend}, add env vars "
                f"`GOOGLE_OAUTH2_KEY` and `GOOGLE_OAUTH2_SECRET`."
            )
            logger.warning(msg)
            raise KeyNotConfigured(
                f"{msg}\nRefer to: "
                "https://developers.google.com/identity/protocols/oauth2#1.-"
                "obtain-oauth-2.0-credentials-from-the-dynamic_data.setvar."
                "console_name-."
            )

        random = str(uuid.uuid4())
        user_id = request.user.user_id
        org_id = UserSessionUtils.get_organization_id(request)
        cache_key = f"oauth:{org_id}|{user_id}|{backend}|{random}"
        logger.info(f"Generated cache key: {cache_key}")
        return Response(
            status=status.HTTP_200_OK,
            data={"cache_key": f"{cache_key}"},
        )
