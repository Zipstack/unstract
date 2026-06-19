import logging
import uuid
from typing import Any

from django.db import IntegrityError
from django.db.models import ProtectedError, QuerySet
from django.http import HttpRequest
from django.http.response import HttpResponse
from permissions.co_owner_views import CoOwnerManagementMixin
from permissions.permission import (
    IsFrictionLessAdapter,
    IsFrictionLessAdapterDelete,
    IsOwner,
    IsOwnerOrSharedUserOrSharedToOrg,
)
from permissions.resource_share_views import ResourceShareManagementMixin
from plugins import get_plugin
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from tenant_account_v2.organization_member_service import OrganizationMemberService
from tool_instance_v2.models import ToolInstance
from utils.filtering import FilterHelper

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.constants import AdapterKeys
from adapter_processor_v2.exceptions import (
    CannotDeleteDefaultAdapter,
    DeleteAdapterInUseError,
    DuplicateAdapterNameError,
    IdIsMandatory,
    InValidType,
)
from adapter_processor_v2.serializers import (
    AdapterInfoSerializer,
    AdapterInstanceSerializer,
    AdapterListSerializer,
    DefaultAdapterSerializer,
    SharedUserListSerializer,
    TestAdapterSerializer,
    UserDefaultAdapterSerializer,
)

from .constants import AdapterKeys as constant
from .models import AdapterInstance, UserDefaultAdapter

notification_plugin = get_plugin("notification")
if notification_plugin:
    from plugins.notification.constants import ResourceType

logger = logging.getLogger(__name__)


class DefaultAdapterViewSet(ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = DefaultAdapterSerializer

    def configure_default_triad(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> HttpResponse:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Convert request data to json
        default_triad = request.data
        AdapterProcessor.set_default_triad(default_triad, request.user)
        return Response(status=status.HTTP_200_OK)

    def get_default_triad(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> HttpResponse:
        try:
            organization_member = OrganizationMemberService.get_user_by_id(
                request.user.id
            )
            user_default_adapter = UserDefaultAdapter.objects.get(
                organization_member=organization_member
            )
            serializer = UserDefaultAdapterSerializer(user_default_adapter).data
            return Response(serializer)

        except UserDefaultAdapter.DoesNotExist:
            # Handle the case when no records are found
            return Response(status=status.HTTP_200_OK, data={})


class AdapterViewSet(GenericViewSet):
    versioning_class = URLPathVersioning
    serializer_class = TestAdapterSerializer

    def list(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> HttpResponse:
        if request.method == "GET":
            adapter_type = request.GET.get(AdapterKeys.ADAPTER_TYPE)
            if (
                adapter_type == AdapterKeys.LLM
                or adapter_type == AdapterKeys.EMBEDDING
                or adapter_type == AdapterKeys.VECTOR_DB
                or adapter_type == AdapterKeys.X2TEXT
                or adapter_type == AdapterKeys.OCR
            ):
                json_schema = AdapterProcessor.get_all_supported_adapters(
                    type=adapter_type, user_email=request.user.email
                )
                return Response(json_schema, status=status.HTTP_200_OK)
            else:
                raise InValidType

    def get_adapter_schema(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> HttpResponse:
        if request.method == "GET":
            adapter_name = request.GET.get(AdapterKeys.ID)
            if adapter_name is None or adapter_name == "":
                raise IdIsMandatory()
            json_schema = AdapterProcessor.get_json_schema(adapter_id=adapter_name)
            return Response(data=json_schema, status=status.HTTP_200_OK)

    def test(self, request: Request) -> Response:
        """Tests the connector against the credentials passed."""
        serializer: AdapterInstanceSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adapter_id = serializer.validated_data.get(AdapterKeys.ADAPTER_ID)
        adapter_metadata = serializer.validated_data.get(AdapterKeys.ADAPTER_METADATA)
        adapter_metadata[AdapterKeys.ADAPTER_TYPE] = serializer.validated_data.get(
            AdapterKeys.ADAPTER_TYPE
        )
        test_result = AdapterProcessor.test_adapter(
            adapter_id=adapter_id, adapter_metadata=adapter_metadata
        )
        return Response(
            {AdapterKeys.IS_VALID: test_result},
            status=status.HTTP_200_OK,
        )


class AdapterInstanceViewSet(
    CoOwnerManagementMixin, ResourceShareManagementMixin, ModelViewSet
):
    serializer_class = AdapterInstanceSerializer
    notification_resource_name_field = "adapter_name"

    def get_notification_resource_type(self, resource: Any) -> str | None:
        try:
            from plugins.notification.constants import ResourceType
        except ImportError:
            logger.debug(
                "Notification plugin not available, skipping resource type lookup"
            )
            return None

        adapter_type_to_resource = {
            "LLM": ResourceType.LLM.value,
            "EMBEDDING": ResourceType.EMBEDDING.value,
            "VECTOR_DB": ResourceType.VECTOR_DB.value,
            "X2TEXT": ResourceType.X2TEXT.value,
        }
        return adapter_type_to_resource.get(resource.adapter_type)

    def get_permissions(self) -> list[Any]:
        # Frictionless adapters: hidden from non-owners (update/retrieve),
        # deletable by any org member. Others use owner / shared-user gating.
        if self.action in ["update", "partial_update", "retrieve"]:
            return [IsFrictionLessAdapter()]
        if self.action == "destroy":
            return [IsFrictionLessAdapterDelete()]
        if self.action in [
            "list_of_shared_users",
            "adapter_info",
            "share",
            "effective_members",
        ]:
            return [IsOwnerOrSharedUserOrSharedToOrg()]

        elif self.action in ["add_co_owner", "remove_co_owner"]:
            return [IsOwner()]

        # Hack for friction-less onboarding
        # User cant view/update metadata but can delete/share etc
        return [IsOwner()]

    def get_queryset(self) -> QuerySet | None:
        queryset = AdapterInstance.objects.for_user(self.request.user)
        if filter_args := FilterHelper.build_filter_args(
            self.request,
            constant.ADAPTER_TYPE,
            constant.ADAPTER_NAME,
        ):
            queryset = queryset.filter(**filter_args)
        return queryset.prefetch_related("co_owners")

    def get_serializer_class(
        self,
    ) -> ModelSerializer:
        if self.action == "list":
            return AdapterListSerializer
        return AdapterInstanceSerializer

    def create(self, request: Any) -> Response:
        serializer = self.get_serializer(data=request.data)

        use_platform_unstract_key = False
        adapter_metadata = request.data.get(AdapterKeys.ADAPTER_METADATA)
        if adapter_metadata and adapter_metadata.get(
            AdapterKeys.PLATFORM_PROVIDED_UNSTRACT_KEY, False
        ):
            use_platform_unstract_key = True

        serializer.is_valid(raise_exception=True)
        try:
            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)

            if adapter_type == AdapterKeys.X2TEXT and use_platform_unstract_key:
                adapter_metadata_b = serializer.validated_data.get(
                    AdapterKeys.ADAPTER_METADATA_B
                )
                adapter_metadata_b = AdapterProcessor.update_adapter_metadata(
                    adapter_metadata_b
                )
                # Update the validated data with the new adapter_metadata
                serializer.validated_data[AdapterKeys.ADAPTER_METADATA_B] = (
                    adapter_metadata_b
                )

            instance = serializer.save()
            organization_member = OrganizationMemberService.get_user_by_id(
                request.user.id
            )

            # Check to see if there is a default configured
            # for this adapter_type and for the current user
            (
                user_default_adapter,
                created,
            ) = UserDefaultAdapter.objects.get_or_create(
                organization_member=organization_member
            )

            if (adapter_type == AdapterKeys.LLM) and (
                not user_default_adapter.default_llm_adapter
            ):
                user_default_adapter.default_llm_adapter = instance

            elif (adapter_type == AdapterKeys.EMBEDDING) and (
                not user_default_adapter.default_embedding_adapter
            ):
                user_default_adapter.default_embedding_adapter = instance
            elif (adapter_type == AdapterKeys.VECTOR_DB) and (
                not user_default_adapter.default_vector_db_adapter
            ):
                user_default_adapter.default_vector_db_adapter = instance
            elif (adapter_type == AdapterKeys.X2TEXT) and (
                not user_default_adapter.default_x2text_adapter
            ):
                user_default_adapter.default_x2text_adapter = instance

            organization_member = OrganizationMemberService.get_user_by_id(
                request.user.id
            )
            user_default_adapter.organization_member = organization_member

            user_default_adapter.save()

        except IntegrityError:
            raise DuplicateAdapterNameError(
                name=serializer.validated_data.get(AdapterKeys.ADAPTER_NAME)
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @staticmethod
    def _adapter_used_in_tool_instance(adapter: AdapterInstance) -> bool:
        """True if any workflow tool instance in the adapter's org references
        it via metadata. These refs are JSON values (post lazy-migration the
        adapter id; before it, the adapter name), so no FK protects them.
        """
        needles = {str(adapter.id), adapter.adapter_name}

        # metadata is free-form JSON: walk every nested value so a reference
        # nested in a sub-object isn't missed, and tolerate non-dict payloads
        # (list/scalar/None) that would otherwise blow up on .values().
        def contains_ref(value: Any) -> bool:
            if isinstance(value, str):
                return value in needles
            if isinstance(value, dict):
                return any(contains_ref(v) for v in value.values())
            if isinstance(value, list):
                return any(contains_ref(v) for v in value)
            return False

        # Linear scan over the org's tool instances — acceptable for an
        # infrequent, interactive delete.
        metadatas = ToolInstance.objects.filter(
            workflow__organization=adapter.organization
        ).values_list("metadata", flat=True)
        return any(contains_ref(metadata) for metadata in metadatas)

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        adapter_instance: AdapterInstance = self.get_object()
        adapter_type = adapter_instance.adapter_type
        try:
            organization_member = OrganizationMemberService.get_user_by_id(
                request.user.id
            )
            user_default_adapter: UserDefaultAdapter = UserDefaultAdapter.objects.get(
                organization_member=organization_member
            )

            if (
                (
                    adapter_type == AdapterKeys.LLM
                    and adapter_instance == user_default_adapter.default_llm_adapter
                )
                or (
                    adapter_type == AdapterKeys.EMBEDDING
                    and adapter_instance == user_default_adapter.default_embedding_adapter
                )
                or (
                    adapter_type == AdapterKeys.VECTOR_DB
                    and adapter_instance == user_default_adapter.default_vector_db_adapter
                )
                or (
                    adapter_type == AdapterKeys.X2TEXT
                    and adapter_instance == user_default_adapter.default_x2text_adapter
                )
            ):
                logger.error("Cannot delete a default adapter")
                raise CannotDeleteDefaultAdapter()
        except UserDefaultAdapter.DoesNotExist:
            # We can go head and remove adapter here
            logger.info("User default adpater doesnt not exist")

        # Adapter refs inside ToolInstance.metadata are JSON values, not FKs,
        # so the DB can't PROTECT them — block here to avoid leaving dangling
        # references. (FK uses are caught by ProtectedError below.)
        if self._adapter_used_in_tool_instance(adapter_instance):
            logger.error(
                f"Cannot delete adapter {adapter_instance.adapter_id}"
                " — referenced by a workflow tool instance"
            )
            raise DeleteAdapterInUseError(adapter_name=adapter_instance.adapter_name)

        try:
            super().perform_destroy(adapter_instance)
        except ProtectedError:
            logger.error(
                f"Failed to delete adapter: {adapter_instance.adapter_id}"
                f" named {adapter_instance.adapter_name}"
            )
            # TODO: Provide details of adpter usage with exception object
            raise DeleteAdapterInUseError(adapter_name=adapter_instance.adapter_name)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def partial_update(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        adapter = self.get_object()
        before = self.snapshot_share_axes(adapter)

        response = super().partial_update(request, *args, **kwargs)
        if response.status_code == 200 and notification_plugin:
            self._notify_shared_users(adapter, before, request.data, request.user)
        return response

    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request: Request, pk: str | None = None) -> Response:
        """Apply share state, then clear default-adapter links for any user
        who lost access.

        ``shared_users`` is read-only on the serializer, so unsharing happens
        only here (not via ``partial_update``). Diff *effective* access
        (direct + group + org) before/after the commit so cleanup also covers
        users who lose access via a group-unshare or ``shared_to_org``
        toggle-off, not just direct removals.
        """
        adapter = self.get_object()
        before_user_ids = self._effective_member_ids(adapter)
        response = super().share(request, pk)
        if response.status_code == status.HTTP_200_OK:
            adapter.refresh_from_db()
            after_user_ids = self._effective_member_ids(adapter)
            removed = before_user_ids - after_user_ids
            # The owner always retains access via ``created_by``; never clear
            # their defaults on a share-axis change (e.g. a ``shared_to_org``
            # toggle-off, which drops the owner from the org-member set).
            removed.discard(adapter.created_by_id)
            self._clear_default_adapter_for_removed_users(adapter, removed)
        return response

    @staticmethod
    def _effective_member_ids(adapter: AdapterInstance) -> set[int]:
        """User ids with effective access to ``adapter`` (direct/group/org)."""
        from tenant_account_v2.sharing_helpers import compute_effective_members

        return {member["user_id"] for member in compute_effective_members(adapter)}

    def _notify_shared_users(
        self,
        adapter: AdapterInstance,
        before: dict[str, set[Any]],
        request_data: dict[str, Any],
        actor: Any,
    ) -> None:
        """Email users newly added to ``shared_users`` (best-effort)."""
        users_diff = self.diff_share_axes(adapter, before, request_data).get(
            "shared_users"
        )
        if not (users_diff and users_diff.added):
            return
        try:
            adapter_type_to_resource = {
                "LLM": ResourceType.LLM.value,
                "EMBEDDING": ResourceType.EMBEDDING.value,
                "VECTOR_DB": ResourceType.VECTOR_DB.value,
                "X2TEXT": ResourceType.X2TEXT.value,
            }
            resource_type = adapter_type_to_resource.get(
                adapter.adapter_type, ResourceType.LLM.value
            )
            service_class = notification_plugin["service_class"]
            notification_service = service_class()
            notification_service.send_sharing_notification(
                resource_type=resource_type,
                resource_name=adapter.adapter_name,
                resource_id=str(adapter.id),
                shared_by=actor,
                shared_to=list(users_diff.added),
                resource_instance=adapter,
            )
        except Exception as e:
            logger.exception("Failed to send sharing notification: %s", e)

    def _clear_default_adapter_for_removed_users(
        self,
        adapter: AdapterInstance,
        removed_user_ids: set[int],
    ) -> None:
        """Null out ``UserDefaultAdapter`` rows pointing at ``adapter`` for
        users who just lost access via the ``share`` action.
        """
        adapter_fields = (
            "default_llm_adapter",
            "default_embedding_adapter",
            "default_vector_db_adapter",
            "default_x2text_adapter",
        )

        for user_id in removed_user_ids:
            try:
                organization_member = OrganizationMemberService.get_user_by_id(id=user_id)
                user_default_adapter = UserDefaultAdapter.objects.get(
                    organization_member=organization_member
                )
            except UserDefaultAdapter.DoesNotExist:
                logger.debug(
                    "User id : %s doesnt have default adapters configured",
                    user_id,
                )
                continue

            updated = False
            for field_name in adapter_fields:
                if getattr(user_default_adapter, field_name) == adapter:
                    setattr(user_default_adapter, field_name, None)
                    updated = True
            if updated:
                # Best-effort: the share already committed, so log a cleanup
                # failure instead of letting it surface as a 500 on a successful
                # share or silently disappear.
                try:
                    user_default_adapter.save()
                except Exception:
                    logger.exception(
                        "Failed clearing default adapter for user_id=%s after "
                        "share on adapter=%s",
                        user_id,
                        adapter.id,
                    )

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:
        adapter = self.get_object()

        serialized_instances = SharedUserListSerializer(adapter).data

        return Response(serialized_instances)

    def update(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        # Check if adapter metadata is being updated and contains the platform key flag
        use_platform_unstract_key = False
        adapter_metadata = request.data.get(AdapterKeys.ADAPTER_METADATA)

        if adapter_metadata and adapter_metadata.get(
            AdapterKeys.PLATFORM_PROVIDED_UNSTRACT_KEY, False
        ):
            use_platform_unstract_key = True
            logger.error(f"Platform key flag detected: {use_platform_unstract_key}")

        # Get the adapter instance for update
        adapter = self.get_object()

        if use_platform_unstract_key:
            logger.error("Processing adapter with platform key")
            serializer = self.get_serializer(adapter, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)

            # Get adapter_type from validated data (consistent with create method)
            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)
            logger.error(f"Adapter type from validated data: {adapter_type}")

            if adapter_type == AdapterKeys.X2TEXT:
                logger.error("Processing X2TEXT adapter with platform key")
                adapter_metadata_b = serializer.validated_data.get(
                    AdapterKeys.ADAPTER_METADATA_B
                )
                adapter_metadata_b = AdapterProcessor.update_adapter_metadata(
                    adapter_metadata_b, is_paid_subscription=True
                )
                # Update the validated data with the new adapter_metadata
                serializer.validated_data[AdapterKeys.ADAPTER_METADATA_B] = (
                    adapter_metadata_b
                )

            # Save the instance with updated metadata
            serializer.save()
            return Response(serializer.data)

        # For non-platform-key cases, use the default update behavior
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def adapter_info(self, request: HttpRequest, pk: uuid) -> Response:
        adapter = self.get_object()

        serialized_instances = AdapterInfoSerializer(adapter).data

        return Response(serialized_instances)
