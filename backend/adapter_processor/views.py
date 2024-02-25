import logging
from typing import Any, Optional

from account.models import User
from adapter_processor.adapter_processor import AdapterProcessor
from adapter_processor.constants import AdapterKeys
from adapter_processor.exceptions import (
    CannotDeleteDefaultAdapter,
    IdIsMandatory,
    InValidType,
    UniqueConstraintViolation,
)
from adapter_processor.serializers import (
    AdapterDetailSerializer,
    AdapterInstanceSerializer,
    DefaultAdapterSerializer,
    TestAdapterSerializer,
)
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http.response import HttpResponse
from permissions.permission import IsOwner
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from utils.filtering import FilterHelper

from .constants import AdapterKeys as constant
from .exceptions import InternalServiceError
from .models import AdapterInstance

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
            json_schema = AdapterProcessor.get_json_schema(
                adapter_id=adapter_name
            )
            return Response(data=json_schema, status=status.HTTP_200_OK)

    def test(self, request: Request) -> Response:
        """Tests the connector against the credentials passed."""
        serializer: AdapterInstanceSerializer = self.get_serializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        adapter_id = serializer.validated_data.get(AdapterKeys.ADAPTER_ID)
        adapter_metadata = serializer.validated_data.get(
            AdapterKeys.ADAPTER_METADATA
        )
        adapter_metadata[
            AdapterKeys.ADAPTER_TYPE
        ] = serializer.validated_data.get(AdapterKeys.ADAPTER_TYPE)
        test_result = AdapterProcessor.test_adapter(
            adapter_id=adapter_id, adapter_metadata=adapter_metadata
        )
        return Response(
            {AdapterKeys.IS_VALID: test_result},
            status=status.HTTP_200_OK,
        )


class AdapterInstanceViewSet(ModelViewSet):
    queryset = AdapterInstance.objects.all()

    serializer_class = AdapterInstanceSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        if filter_args := FilterHelper.build_filter_args(
            self.request,
            constant.ADAPTER_TYPE,
        ):
            queryset = AdapterInstance.objects.filter(
                created_by=self.request.user, **filter_args
            )
        else:
            queryset = AdapterInstance.objects.filter(
                created_by=self.request.user
            )
        return queryset

    def create(self, request: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            # Check to see if there is a default configured
            # for this adapter_type and for the current user
            existing_adapter_default = self.get_existing_defaults(
                request.data, request.user
            )
            # If there is no default, then make this one as default
            if existing_adapter_default is None:
                # Update the adapter_instance to is_default=True
                serializer.validated_data[AdapterKeys.IS_DEFAULT] = True

            serializer.save()
        except IntegrityError:
            raise UniqueConstraintViolation(
                f"{AdapterKeys.ADAPTER_NAME_EXISTS}"
            )
        except Exception as e:
            logger.error(f"Error saving adapter to DB: {e}")
            raise InternalServiceError
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def get_existing_defaults(
        self, adapter_config: dict[str, Any], user: User
    ) -> Optional[AdapterInstance]:
        filter_params: dict[str, Any] = {}
        adapter_type = adapter_config.get(AdapterKeys.ADAPTER_TYPE)
        filter_params["adapter_type"] = adapter_type
        filter_params["is_default"] = True
        filter_params["created_by"] = user
        existing_adapter_default: AdapterInstance = (
            AdapterInstance.objects.filter(**filter_params).first()
        )

        return existing_adapter_default


class AdapterDetailViewSet(ModelViewSet):
    queryset = AdapterInstance.objects.all()
    serializer_class = AdapterDetailSerializer
    permission_classes = [IsOwner]

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        adapter_instance: AdapterInstance = self.get_object()
        if adapter_instance.is_default:
            logger.error("Cannot delete a default adapter")
            raise CannotDeleteDefaultAdapter
        super().perform_destroy(adapter_instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
