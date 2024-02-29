import logging
from typing import Any, Optional

from apps.app_deployment.exceptions import AppDeploymentBadRequestException
from apps.app_deployment.helpers.dns_provider import get_dns_provider
from apps.app_deployment.models import AppDeployment
from apps.app_deployment.serializers import (
    AppDeploymentListSerializer,
    AppDeploymentResponseSerializer,
    AppDeploymentSerializer,
)
from apps.traffic_routing.models import TrafficRule
from django.conf import settings
from django.db import connection
from django.db.models.query import QuerySet
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from backend.constants import RequestKey
from utils.filtering import FilterHelper

Logger = logging.getLogger(__name__)


# Create your views here.
class AppDeploymentView(viewsets.ModelViewSet):
    """APP deployment view.

    Args:
        viewsets (_type_): _description_

    Raises:
        InvalidAPIRequest: _description_
        ApiDeploymentBadRequestException: _description_

    Returns:
        _type_: _description_
    """

    queryset = AppDeployment.objects.all()

    def get_queryset(self) -> QuerySet:
        """Adding additional filters and default sorting.

        Returns:
            QuerySet: _description_
        """
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.CREATED_BY,
            RequestKey.IS_ACTIVE,
        )
        queryset = (
            AppDeployment.objects.filter(**filter_args)
            if filter_args
            else AppDeployment.objects.all()
        )

        order_by = self.request.query_params.get("order_by")
        if order_by == "desc":
            queryset = queryset.order_by("-modified_at")
        elif order_by == "asc":
            queryset = queryset.order_by("modified_at")

        return queryset

    def get_serializer_class(self) -> serializers.Serializer:
        """Method to return the serializer class.

        Returns:
            serializers.Serializer: _description_
        """
        if self.action in ["list"]:
            return AppDeploymentListSerializer
        return AppDeploymentSerializer

    @action(detail=True, methods=["get"])
    def fetch_one(self, request: Request, pk: Optional[str] = None) -> Response:
        """Custom action to fetch a single instance."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        """Create a new AppDeployment instance.

        Args:
            request (Request): The HTTP request object.
            *args (tuple[Any]): Additional positional arguments.
            **kwargs (dict[str, Any]): Additional keyword arguments.

        Returns:
            Response: The HTTP response containing the serialized data of
                      the created instance.

        Raises:
            AppDeploymentBadRequestException: If the serializer is not valid.

        Notes:
            This method creates a new AppDeployment instance based on
            the provided data in the request.
            It first validates the serializer data and raises an exception
            if it is not valid.
            Then, it creates a DNS record using the DNS provider and
            the subdomain from the serializer data.
            After that, it retrieves the domain details from the DNS provider.
            Finally, it saves the serializer data with the retrieved domain
            details and returns the serialized data in the response.
        """
        #  TODO: Consider using transaction for atomic operations
        serializer: Serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # domain creation - DNS provider, record_id
        # APP_TEMPLATE_DOMAIN is where the template will be originally deployed
        dns_provider = get_dns_provider(
            serializer.validated_data.get("subdomain"),
            settings.APP_TEMPLATE_DOMAIN,
        )
        domain_details = dns_provider.get_domain_components()
        dns_fqdn = domain_details["fqdn"]
        dns_domain = domain_details["domain"]
        dns_top_level_domain = domain_details["top_level_domain"]

        #  Check if the domain exist in routing table before creating dns record
        try:
            existing_rule = TrafficRule.objects.get(fqdn=dns_fqdn)
            Logger.error(
                "Subdomain record already exists with in routing table: %s",
                existing_rule,
            )
            raise AppDeploymentBadRequestException(
                f"Subdomain({domain_details.get('subdomain')}) already in use"
            )
        except TrafficRule.DoesNotExist:
            #  Do nothing and continue since no record exists
            pass

        # Creates DNS record
        dns_provider.create_record()

        # Saves data in app_deployment table
        saved_app = serializer.save(
            dns_domain=dns_domain,
            dns_top_level_domain=dns_top_level_domain,
            dns_provider=settings.DNS_PROVIDER,
        )

        # Saves traffic rule details in the public table
        TrafficRule(
            fqdn=dns_fqdn,
            rule={
                "service": settings.APP_TEMPLATE_SERVICE,
                "rule": f"Host(`{dns_fqdn}`)",
            },
            app_deployment_id=saved_app.id,
            organization=connection.get_tenant(),
            created_by=request.user,
        ).save()

        response_serializer = AppDeploymentResponseSerializer(
            {**serializer.data}
        )

        headers = self.get_success_headers(serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


def get_error_from_serializer(error_details: dict[str, Any]) -> Optional[str]:
    """Method to return first error message.

    Args:
        error_details (dict[str, Any]): _description_

    Returns:
        Optional[str]: _description_
    """
    error_key = next(iter(error_details))
    # Get the first error message
    error_message: str = f"{error_details[error_key][0]} : {error_key}"
    return error_message
