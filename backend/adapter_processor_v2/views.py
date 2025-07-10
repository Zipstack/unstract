import logging
import uuid
from typing import Any

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
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from tenant_account_v2.organization_member_service import OrganizationMemberService
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
        # Check if adapter metadata is being updated and contains the platform key flag
        use_platform_unstract_key = False
        adapter_metadata = request.data.get(AdapterKeys.ADAPTER_METADATA)

        if adapter_metadata and adapter_metadata.get(
            AdapterKeys.PLATFORM_PROVIDED_UNSTRACT_KEY, False
        ):
            use_platform_unstract_key = True
        # Get the adapter instance for update
        adapter = self.get_object()
        if use_platform_unstract_key:
            serializer = self.get_serializer(adapter, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)

            # Get adapter_type from validated data (consistent with create method)
            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)

            if adapter_type == AdapterKeys.X2TEXT:
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

                # Handle shared users if needed
                if AdapterKeys.SHARED_USERS in request.data:
                    self._handle_shared_users_update(request, adapter)

                return Response(serializer.data)
        
        # For non-platform-key cases, handle shared users separately if needed
        if AdapterKeys.SHARED_USERS in request.data:
            self._handle_shared_users_update(request, adapter)

        return super().partial_update(request, *args, **kwargs)

    def _handle_shared_users_update(self, request: Request, adapter: AdapterInstance) -> None:
        """Handle shared users update logic for adapters."""
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

                if user_default_adapter.default_llm_adapter == adapter:
                    user_default_adapter.default_llm_adapter = None
                elif user_default_adapter.default_embedding_adapter == adapter:
                    user_default_adapter.default_embedding_adapter = None
                elif user_default_adapter.default_vector_db_adapter == adapter:
                    user_default_adapter.default_vector_db_adapter = None
                elif user_default_adapter.default_x2text_adapter == adapter:
                    user_default_adapter.default_x2text_adapter = None

                user_default_adapter.save()
            except UserDefaultAdapter.DoesNotExist:
                logger.debug(
                    "User id : %s doesnt have default adapters configured",
                    user_id,
                )
                continue

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:
        adapter = self.get_object()

        serialized_instances = SharedUserListSerializer(adapter).data

        return Response(serialized_instances)

    @action(detail=True, methods=["get"])
    def adapter_info(self, request: HttpRequest, pk: uuid) -> Response:
        adapter = self.get_object()

        serialized_instances = AdapterInfoSerializer(adapter).data

        return Response(serialized_instances)
