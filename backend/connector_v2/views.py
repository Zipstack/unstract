import logging
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from connector_auth_v2.constants import ConnectorAuthKey
from connector_auth_v2.exceptions import CacheMissException, MissingParamException
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.exceptions import OAuthTimeOut
from django.db import IntegrityError
from django.db.models import ProtectedError, QuerySet
from permissions.membership_views import OwnerManagementMixin
from permissions.permission import IsOwner, IsOwnerOrSharedUserOrSharedToOrg
from permissions.resource_share_views import ResourceShareManagementMixin
from permissions.roles import ResourceRole
from plugins import get_plugin
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tenant_account_v2.organization_member_service import OrganizationMemberService
from utils.filtering import FilterHelper
from utils.pagination import OptionalPagination
from utils.user_context import UserContext

from backend.constants import RequestKey
from connector_v2.constants import ConnectorInstanceKey as CIKey
from unstract.connectors.connectorkit import Connectorkit
from unstract.connectors.enums import ConnectorMode

from .exceptions import DeleteConnectorInUseError
from .models import ConnectorInstance
from .serializers import ConnectorInstanceSerializer, SharedUserListSerializer

notification_plugin = get_plugin("notification")
if notification_plugin:
    from plugins.notification.constants import ResourceType
    from plugins.notification.sharing_notification import SharingNotificationService

logger = logging.getLogger(__name__)


class ConnectorInstanceViewSet(
    OwnerManagementMixin, ResourceShareManagementMixin, viewsets.ModelViewSet
):
    versioning_class = URLPathVersioning
    serializer_class = ConnectorInstanceSerializer
    pagination_class = OptionalPagination
    # `pk` tiebreaker keeps paging deterministic when modified_at collides.
    ordering = ["-modified_at", "pk"]
    ordering_fields = ["connector_name", "created_at", "modified_at"]
    notification_resource_name_field = "connector_name"

    def get_notification_resource_type(self, resource: Any) -> str | None:
        if not notification_plugin:
            return None
        return ResourceType.CONNECTOR.value

    def get_permissions(self) -> list[Any]:
        if self.action in [
            "update",
            "destroy",
            "partial_update",
            "add_co_owner",
            "remove_co_owner",
        ]:
            return [IsOwner()]

        return [IsOwnerOrSharedUserOrSharedToOrg()]

    @staticmethod
    def _enforce_connector_creation_restriction(request: Any) -> None:
        """Controlled mode (UN-3585): only org admins may create connectors
        when the org has enabled the restriction. Service accounts (platform
        API-key sessions) bypass; the default (flag off) keeps creation open
        for everyone. Applies to all connector types (all connect to external
        systems).
        """
        if getattr(request.user, "is_service_account", False):
            return
        organization = UserContext.get_organization()
        if (
            organization
            and organization.restrict_connector_creation
            and not OrganizationMemberService.is_user_organization_admin(request.user)
        ):
            raise PermissionDenied(
                "Connector creation is restricted to organization admins. "
                "Please contact your organization admin."
            )

    def get_queryset(self) -> QuerySet | None:
        # Avoid per-row queries for owner/co-owner + creator fields in list views
        queryset = (
            ConnectorInstance.objects.for_user(self.request.user)
            .select_related("created_by")
            .prefetch_related("memberships__user")
        )

        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.WORKFLOW,
            RequestKey.CREATED_BY,
            CIKey.CONNECTOR_TYPE,
            CIKey.CONNECTOR_NAME,
        )
        if filter_args:
            queryset = queryset.filter(**filter_args)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(connector_name__icontains=search)

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
        oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)

        # Only use OAuth flow if connector supports it AND oauth_key is provided
        if ConnectorInstance.supportsOAuth(connector_id=connector_id) and oauth_key:
            oauth_tokens = ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key,
                delete_key=False,  # Don't delete yet - wait for successful operation
            )
            if oauth_tokens is None:
                raise MissingParamException(param=ConnectorAuthKey.OAUTH_KEY)
            # Preserve non-secret form fields (e.g. site_url connector Sharepoint)
            form_metadata = self.request.data.get(CIKey.CONNECTOR_METADATA) or {}
            if not isinstance(form_metadata, dict):
                form_metadata = {}
            connector_metadata = {**form_metadata, **oauth_tokens}
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
        # Explicitly bind the connector to the request-scoped organization.
        # Defense-in-depth: DefaultOrganizationMixin already declares
        # `organization` as editable=False (so DRF drops any client-supplied
        # value) and its save() backfills the org from UserContext when unset.
        # Binding here makes that explicit at the callsite and keeps the row's
        # org consistent with the org the controlled-mode check evaluated.
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            created_by=self.request.user,
            modified_by=self.request.user,
            organization=UserContext.get_organization(),
        )  # type: ignore

        # Clean up OAuth cache after successful create
        self._cleanup_oauth_cache(connector_id)

    def create(self, request: Any) -> Response:
        # Overriding default exception behavior
        # Fail fast on the admin restriction before validating the payload —
        # the check depends only on the request/org, not on validated data, so
        # a denied caller shouldn't get input-validation feedback first.
        self._enforce_connector_creation_restriction(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{CIKey.CONNECTOR_EXISTS}, \
                    {CIKey.DUPLICATE_API}"
            )
        # ``created_by`` is audit-only; the creator's access flows through an
        # OWNER membership row (UN-2202 co-owners).
        serializer.instance.memberships.get_or_create(
            user_id=request.user.id, defaults={"role": ResourceRole.OWNER}
        )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: Request, pk: Any = None) -> Response:
        connector = self.get_object()
        return Response(SharedUserListSerializer(connector).data)

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

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Override to handle sharing notifications."""
        instance = self.get_object()
        before = self.snapshot_share_axes(instance)

        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200 and notification_plugin:
            self._notify_shared_users(instance, before, request.data, request.user)
        return response

    def _notify_shared_users(
        self,
        instance: ConnectorInstance,
        before: dict[str, set[Any]],
        request_data: dict[str, Any],
        actor: Any,
    ) -> None:
        """Email users newly added to ``shared_users`` (best-effort)."""
        users_diff = self.diff_share_axes(instance, before, request_data).get(
            "shared_users"
        )
        if not (users_diff and users_diff.added):
            return
        try:
            SharingNotificationService().send_sharing_notification(
                resource_type=ResourceType.CONNECTOR.value,
                resource_name=instance.connector_name,
                resource_id=str(instance.id),
                shared_by=actor,
                shared_to=list(users_diff.added),
                resource_instance=instance,
            )
            logger.info(
                "Sent sharing notifications for connector to %d users",
                len(users_diff.added),
            )
        except Exception as e:
            logger.exception(
                "Failed to send sharing notification, continuing update though: %s",
                str(e),
            )
