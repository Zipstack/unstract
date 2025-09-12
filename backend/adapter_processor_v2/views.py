import json
import logging
import uuid
from typing import Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import IntegrityError
from django.db.models import ProtectedError, QuerySet
from django.http import HttpRequest
from django.http.response import HttpResponse
from permissions.permission import (
    IsFrictionLessAdapter,
    IsFrictionLessAdapterDelete,
    IsOwner,
    IsOwnerOrSharedUserOrSharedToOrg,
)
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from tenant_account_v2.organization_member_service import (
    OrganizationMemberService,
)
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


class AdapterInstanceViewSet(ModelViewSet):
    serializer_class = AdapterInstanceSerializer

    def get_permissions(self) -> list[Any]:
        if self.action in ["update", "retrieve"]:
            return [IsFrictionLessAdapter()]

        elif self.action == "destroy":
            return [IsFrictionLessAdapterDelete()]

        elif self.action in ["list_of_shared_users", "adapter_info"]:
            return [IsOwnerOrSharedUserOrSharedToOrg()]

        # Hack for friction-less onboarding
        # User cant view/update metadata but can delete/share etc
        return [IsOwner()]

    def get_queryset(self) -> QuerySet | None:
        if filter_args := FilterHelper.build_filter_args(
            self.request,
            constant.ADAPTER_TYPE,
        ):
            queryset = AdapterInstance.objects.for_user(self.request.user).filter(
                **filter_args
            )
        else:
            queryset = AdapterInstance.objects.for_user(self.request.user)
        return queryset

    def get_serializer_class(
        self,
    ) -> ModelSerializer:
        if self.action == "list":
            return AdapterListSerializer
        return AdapterInstanceSerializer

    def _decrypt_and_validate_metadata(self, adapter_metadata_b: bytes) -> dict[str, Any]:
        """Decrypt adapter metadata and validate its format."""
        if not adapter_metadata_b:
            raise ValidationError("Missing adapter metadata for validation.")

        try:
            fernet = Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))
            decrypted_json = fernet.decrypt(adapter_metadata_b)
            decrypted_metadata = json.loads(decrypted_json.decode("utf-8"))

            if not isinstance(decrypted_metadata, dict):
                raise ValidationError(
                    "Invalid adapter metadata format: expected JSON object."
                )
            return decrypted_metadata
        except Exception as e:
            raise ValidationError("Invalid adapter metadata.") from e

    def _validate_adapter_urls(
        self, adapter_id: str, decrypted_metadata: dict[str, Any]
    ) -> None:
        """Validate URLs for adapter configuration."""
        try:
            AdapterProcessor.validate_adapter_urls(adapter_id, decrypted_metadata)
        except Exception as e:
            adapter_name = decrypted_metadata.get(AdapterKeys.ADAPTER_NAME, "adapter")
            error_detail = f"Error testing '{adapter_name}'. {e!s}"
            raise ValidationError(error_detail) from e

    def _check_platform_key_usage(self, request_data: dict[str, Any]) -> bool:
        """Check if platform unstract key should be used."""
        adapter_metadata = request_data.get(AdapterKeys.ADAPTER_METADATA)
        return bool(
            adapter_metadata
            and adapter_metadata.get(AdapterKeys.PLATFORM_PROVIDED_UNSTRACT_KEY, False)
        )

    def _update_metadata_for_platform_key(
        self,
        serializer_validated_data: dict[str, Any],
        adapter_type: str,
        is_paid_subscription: bool = False,
    ) -> None:
        """Update adapter metadata when using platform key."""
        if adapter_type == AdapterKeys.X2TEXT:
            adapter_metadata_b = serializer_validated_data.get(
                AdapterKeys.ADAPTER_METADATA_B
            )
            updated_metadata_b = AdapterProcessor.update_adapter_metadata(
                adapter_metadata_b, is_paid_subscription=is_paid_subscription
            )
            serializer_validated_data[AdapterKeys.ADAPTER_METADATA_B] = updated_metadata_b

    def _set_default_adapter_if_needed(
        self, adapter_instance: AdapterInstance, adapter_type: str, user_id: int
    ) -> None:
        """Set adapter as default if no default exists for this type."""
        organization_member = OrganizationMemberService.get_user_by_id(user_id)
        user_default_adapter, _ = UserDefaultAdapter.objects.get_or_create(
            organization_member=organization_member
        )

        # Map adapter types to their default fields
        adapter_type_mapping = {
            AdapterKeys.LLM: "default_llm_adapter",
            AdapterKeys.EMBEDDING: "default_embedding_adapter",
            AdapterKeys.VECTOR_DB: "default_vector_db_adapter",
            AdapterKeys.X2TEXT: "default_x2text_adapter",
        }

        if adapter_type in adapter_type_mapping:
            field_name = adapter_type_mapping[adapter_type]
            if not getattr(user_default_adapter, field_name):
                setattr(user_default_adapter, field_name, adapter_instance)
                user_default_adapter.organization_member = organization_member
                user_default_adapter.save()

    def _validate_update_metadata(
        self,
        serializer_validated_data: dict[str, Any],
        current_adapter: AdapterInstance,
    ) -> tuple[str | None, dict[str, Any] | None]:
        """Validate metadata for update operations."""
        if AdapterKeys.ADAPTER_METADATA_B not in serializer_validated_data:
            return None, None

        adapter_id = (
            serializer_validated_data.get(AdapterKeys.ADAPTER_ID)
            or current_adapter.adapter_id
        )
        adapter_metadata_b = serializer_validated_data.get(AdapterKeys.ADAPTER_METADATA_B)

        if not adapter_id or not adapter_metadata_b:
            raise ValidationError("Missing adapter metadata for validation.")

        decrypted_metadata = self._decrypt_and_validate_metadata(adapter_metadata_b)
        self._validate_adapter_urls(adapter_id, decrypted_metadata)

        return adapter_id, decrypted_metadata

    def create(self, request: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        use_platform_unstract_key = self._check_platform_key_usage(request.data)

        serializer.is_valid(raise_exception=True)

        # Extract and validate metadata
        adapter_id = serializer.validated_data.get(AdapterKeys.ADAPTER_ID)
        adapter_metadata_b = serializer.validated_data.get(AdapterKeys.ADAPTER_METADATA_B)
        decrypted_metadata = self._decrypt_and_validate_metadata(adapter_metadata_b)

        # Validate URLs for security
        self._validate_adapter_urls(adapter_id, decrypted_metadata)

        try:
            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)

            # Update metadata if using platform key
            if use_platform_unstract_key:
                self._update_metadata_for_platform_key(
                    serializer.validated_data, adapter_type
                )

            # Save the adapter instance
            instance = serializer.save()

            # Set as default adapter if needed
            self._set_default_adapter_if_needed(instance, adapter_type, request.user.id)

        except IntegrityError:
            raise DuplicateAdapterNameError(
                name=serializer.validated_data.get(AdapterKeys.ADAPTER_NAME)
            )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
        if AdapterKeys.SHARED_USERS in request.data:
            # find the deleted users
            adapter = self.get_object()
            shared_users = {
                int(user_id) for user_id in request.data.get("shared_users", {})
            }
            current_users = {user.id for user in adapter.shared_users.all()}
            removed_users = current_users.difference(shared_users)

            # if removed user use this adapter as default
            # Remove the same from his default
            for user_id in removed_users:
                try:
                    organization_member = OrganizationMemberService.get_user_by_id(
                        id=user_id
                    )
                    user_default_adapter: UserDefaultAdapter = (
                        UserDefaultAdapter.objects.get(
                            organization_member=organization_member
                        )
                    )

                    adapter_fields = [
                        "default_llm_adapter",
                        "default_embedding_adapter",
                        "default_vector_db_adapter",
                        "default_x2text_adapter",
                    ]

                    updated = False
                    for field in adapter_fields:
                        if getattr(user_default_adapter, field) == adapter:
                            setattr(user_default_adapter, field, None)
                            updated = True

                    if updated:
                        user_default_adapter.save()
                except UserDefaultAdapter.DoesNotExist:
                    logger.debug(
                        "User id : %s doesnt have default adapters configured",
                        user_id,
                    )
                    continue

        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:
        adapter = self.get_object()

        serialized_instances = SharedUserListSerializer(adapter).data

        return Response(serialized_instances)

    def update(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        use_platform_unstract_key = self._check_platform_key_usage(request.data)
        adapter = self.get_object()

        # Get serializer and validate data
        serializer = self.get_serializer(adapter, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Validate metadata if being updated
        _, _ = self._validate_update_metadata(serializer.validated_data, adapter)

        # Handle platform key updates
        if use_platform_unstract_key:
            logger.error("Processing adapter with platform key")
            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)
            logger.error(f"Adapter type from validated data: {adapter_type}")

            # Update metadata for platform key usage
            self._update_metadata_for_platform_key(
                serializer.validated_data,
                adapter_type,
                is_paid_subscription=True,
            )

            # Save and return updated instance
            serializer.save()
            return Response(serializer.data)

        # For non-platform-key cases, use the default update behavior
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def adapter_info(self, request: HttpRequest, pk: uuid) -> Response:
        adapter = self.get_object()

        serialized_instances = AdapterInfoSerializer(adapter).data

        return Response(serialized_instances)
