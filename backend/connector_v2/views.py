import logging
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from connector_auth_v2.constants import ConnectorAuthKey
from connector_auth_v2.exceptions import CacheMissException, MissingParamException
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.exceptions import OAuthTimeOut
from django.db import IntegrityError
from django.db.models import ProtectedError, QuerySet
from permissions.permission import IsOwner, IsOwnerOrSharedUserOrSharedToOrg
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from backend.constants import RequestKey
from connector_v2.constants import ConnectorInstanceKey as CIKey
from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.enums import ConnectorMode

from .exceptions import DeleteConnectorInUseError
from .models import ConnectorInstance
from .serializers import ConnectorInstanceSerializer

logger = logging.getLogger(__name__)


class ConnectorInstanceViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = ConnectorInstanceSerializer

    def get_permissions(self) -> list[Any]:
        if self.action in ["update", "destroy", "partial_update"]:
            return [IsOwner()]

        return [IsOwnerOrSharedUserOrSharedToOrg()]

    def get_queryset(self) -> QuerySet | None:
        queryset = ConnectorInstance.objects.for_user(self.request.user)

        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.WORKFLOW,
            RequestKey.CREATED_BY,
            CIKey.CONNECTOR_TYPE,
        )
        if filter_args:
            queryset = queryset.filter(**filter_args)

        # Filter by connector_mode
        connector_mode_param = self.request.query_params.get("connector_mode")
        if connector_mode_param:
            try:
                connector_mode = ConnectorMode(connector_mode_param)
                connectors = Connectorkit().get_connectors_list(mode=connector_mode)
                connector_ids = [conn.get("id") for conn in connectors if conn.get("id")]

                if connector_ids:
                    queryset = queryset.filter(connector_id__in=connector_ids)
                else:
                    queryset = queryset.none()
            except ValueError:
                logger.warning(
                    f"Invalid connector_mode parameter: {connector_mode_param}"
                )
                queryset = queryset.none()

        return queryset

    def _get_connector_metadata(self, connector_id: str) -> dict[str, str] | None:
        """Gets connector metadata for the ConnectorInstance.


        Raises:
            e: MissingParamException, CacheMissException

        Returns:
            dict[str, str]: Connector creds dict to connect with
        """
        connector_metadata = None
        if ConnectorInstance.supportsOAuth(connector_id=connector_id):
            logger.info(f"Fetching oauth data for {connector_id}")
            oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)
            if not oauth_key:
                raise MissingParamException(
                    "OAuth authentication required. Please sign in with Google first."
                )
            logger.info(f"Using OAuth cache key for {connector_id}")
            connector_metadata = ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key,
                delete_key=False,  # Don't delete yet - wait for successful operation
            )
            if connector_metadata is None:
                raise MissingParamException(param=ConnectorAuthKey.OAUTH_KEY)
        else:
            connector_metadata = self.request.data.get(CIKey.CONNECTOR_METADATA)
        return connector_metadata

    def _cleanup_oauth_cache(self, connector_id: str) -> None:
        """Clean up OAuth cache after successful operation."""
        if not ConnectorInstance.supportsOAuth(connector_id=connector_id):
            return

        oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)
        if not oauth_key:
            return
        logger.info(f"Cleaning up OAuth cache for {connector_id}")
        try:
            ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key,
                delete_key=True,  # Delete after successful operation
            )
        except CacheMissException:
            logger.debug("OAuth cache already cleared for %s", connector_id)
        except Exception:
            logger.warning(
                "Failed to clean up OAuth cache for %s", connector_id, exc_info=True
            )

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

        # Clean up OAuth cache after successful update
        self._cleanup_oauth_cache(connector_id)

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

        # Clean up OAuth cache after successful create
        self._cleanup_oauth_cache(connector_id)

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

    def perform_destroy(self, instance: ConnectorInstance) -> None:
        """Override perform_destroy to handle ProtectedError gracefully.

        Args:
            instance: The ConnectorInstance to be deleted

        Raises:
            DeleteConnectorInUseError: If the connector is being used in workflows
        """
        try:
            super().perform_destroy(instance)
        except ProtectedError:
            logger.error(
                f"Failed to delete connector: {instance.connector_id}"
                f" named {instance.connector_name}"
            )
            raise DeleteConnectorInUseError(connector_name=instance.connector_name)
