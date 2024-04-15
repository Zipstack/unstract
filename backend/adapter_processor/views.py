import logging
from typing import Any, Optional

from adapter_processor.adapter_processor import AdapterProcessor
from adapter_processor.constants import AdapterKeys
from adapter_processor.exceptions import (
    CannotDeleteDefaultAdapter,
    DeleteAdapterInUseError,
    IdIsMandatory,
    InValidType,
    UniqueConstraintViolation,
)
from adapter_processor.serializers import (
    AdapterInstanceSerializer,
    AdapterListSerializer,
    DefaultAdapterSerializer,
    SharedUserListSerializer,
    TestAdapterSerializer,
    UserDefaultAdapterSerializer,
)
from django.db import IntegrityError
from django.db.models import ProtectedError, QuerySet
from django.http import HttpRequest
from django.http.response import HttpResponse
from permissions.permission import IsOwner, IsOwnerOrSharedUser
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from utils.filtering import FilterHelper

from .constants import AdapterKeys as constant
from .exceptions import InternalServiceError
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
            user_default_adapter = UserDefaultAdapter.objects.get(user=request.user)
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
                    type=adapter_type
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
        try:
            test_result = AdapterProcessor.test_adapter(
                adapter_id=adapter_id, adapter_metadata=adapter_metadata
            )
            return Response(
                {AdapterKeys.IS_VALID: test_result},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Error testing adapter : {str(e)}")
            raise e


class AdapterInstanceViewSet(ModelViewSet):
    permission_classes: list[type[IsOwner]] = [IsOwner]
    serializer_class = AdapterInstanceSerializer

    def get_queryset(self) -> Optional[QuerySet]:
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
        serializer.is_valid(raise_exception=True)
        try:
            instance = serializer.save()

            # Check to see if there is a default configured
            # for this adapter_type and for the current user
            (
                user_default_adapter,
                created,
            ) = UserDefaultAdapter.objects.get_or_create(user=request.user)

            adapter_type = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)
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

            user_default_adapter.save()

        except IntegrityError:
            raise UniqueConstraintViolation(f"{AdapterKeys.ADAPTER_NAME_EXISTS}")
        except Exception as e:
            logger.error(f"Error saving adapter to DB: {e}")
            raise InternalServiceError
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        adapter_instance: AdapterInstance = self.get_object()
        adapter_type = adapter_instance.adapter_type
        user_default_adapter = UserDefaultAdapter.objects.get(user=request.user)
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
                    user_default_adapter = UserDefaultAdapter.objects.get(
                        user_id=user_id
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

        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def list_of_shared_users(self, request: HttpRequest, pk: Any = None) -> Response:
        self.permission_classes = [IsOwnerOrSharedUser]
        adapter = (
            self.get_object()
        )  # Assuming you have a get_object method in your viewset

        serialized_instances = SharedUserListSerializer(adapter).data

        return Response(serialized_instances)
