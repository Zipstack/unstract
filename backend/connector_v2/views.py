import logging
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from connector_auth_v2.constants import ConnectorAuthKey
from connector_auth_v2.exceptions import CacheMissException, MissingParamException
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.exceptions import OAuthTimeOut
from django.db import IntegrityError
from django.db.models import QuerySet
from permissions.permission import IsOwner
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from backend.constants import RequestKey
from connector_v2.constants import ConnectorInstanceKey as CIKey

from .models import ConnectorInstance
from .serializers import ConnectorInstanceSerializer

logger = logging.getLogger(__name__)


class ConnectorInstanceViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = ConnectorInstanceSerializer

    def get_permissions(self) -> list[Any]:
        return [IsOwner()]

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.WORKFLOW,
            RequestKey.CREATED_BY,
            CIKey.CONNECTOR_TYPE,
            CIKey.CONNECTOR_MODE,
        )
        if filter_args:
            queryset = ConnectorInstance.objects.for_user(self.request.user).filter(
                **filter_args
            )
        else:
            queryset = ConnectorInstance.objects.for_user(self.request.user)
        return queryset

    def _get_connector_metadata(self, connector_id: str) -> dict[str, str] | None:
        """Gets connector metadata for the ConnectorInstance.

        For non oauth based - obtains from request
        For oauth based - obtains from cache

        Raises:
            e: MissingParamException, CacheMissException

        Returns:
            dict[str, str]: Connector creds dict to connect with
        """
        connector_metadata = None
        if ConnectorInstance.supportsOAuth(connector_id=connector_id):
            logger.info(f"Fetching oauth data for {connector_id}")
            oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)
            if oauth_key is None:
                raise MissingParamException(param=ConnectorAuthKey.OAUTH_KEY)
            # Preserve OAuth cache for reuse across multiple operations (Test Connection, Submit,
            # File System browsing). Frontend localStorage stores cache keys which must correspond
            # to persistent backend credentials for tab switching and repeated operations to work.
            connector_metadata = ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key,
                delete_key=False,  # Keep cache - frontend persistence depends on backend credential storage
            )
            if connector_metadata is None:
                raise CacheMissException(
                    f"Couldn't find credentials for {oauth_key} from cache"
                )
        else:
            connector_metadata = self.request.data.get(CIKey.CONNECTOR_METADATA)
        return connector_metadata

    def perform_update(self, serializer: ConnectorInstanceSerializer) -> None:
        connector_metadata = None
        connector_id = self.request.data.get(
            CIKey.CONNECTOR_ID, serializer.instance.connector_id
        )
        try:
            connector_metadata = self._get_connector_metadata(connector_id)
        # TODO: Handle specific exceptions instead of using a generic Exception.
        except Exception:
            # Suppress here to not shout during partial updates
            pass
        # Take metadata from instance itself since update
        # is performed on other fields of ConnectorInstance
        if connector_metadata is None:
            connector_metadata = serializer.instance.connector_metadata
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            modified_by=self.request.user,
        )  # type: ignore

    def perform_create(self, serializer: ConnectorInstanceSerializer) -> None:
        connector_metadata = None
        connector_id = self.request.data.get(CIKey.CONNECTOR_ID)
        try:
            connector_metadata = self._get_connector_metadata(connector_id=connector_id)
        # TODO: Handle specific exceptions instead of using a generic Exception.
        except Exception as exc:
            logger.error(f"Error while obtaining ConnectorAuth: {exc}")
            raise OAuthTimeOut
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            created_by=self.request.user,
            modified_by=self.request.user,
        )  # type: ignore

    def create(self, request: Any) -> Response:
        # Overriding default exception behavior
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{CIKey.CONNECTOR_EXISTS}, \
                    {CIKey.DUPLICATE_API}"
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
