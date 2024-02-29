"""Module to handle app deployment routing globally."""
import logging

from account.authentication_controller import AuthenticationController
from account.dto import OrganizationData
from api.exceptions import APINotFound, Forbidden
from apps.traffic_routing.models import TrafficRule
from django.db import connection
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.request import Request

Logger = logging.getLogger(__name__)


class TrafficRuleListView(viewsets.ModelViewSet):
    """A class representing a view for retrieving traffic rules from the
    database.

    This class extends the `ModelViewSet` class from the `rest_framework`
    module.

    Attributes:
        queryset (QuerySet): The queryset used to retrieve traffic rules from
        the database.
        serializer_class (Serializer): The serializer class used to serialize
        traffic rules.

    Methods:
        get(request: Request) -> JsonResponse: Retrieves traffic rules from the
        database and returns them as a JSON response.
        get_app_and_org(self, request: Request) -> JsonResponse: Retrieves app
        details and organization details from global traffic rules and checks
        user access.
    """

    def get(self, request: Request) -> JsonResponse:
        """A class representing a view for retrieving traffic rules from the
        database.

        This class extends the `ModelViewSet` class from the `rest_framework`
        module.

        Attributes:
            queryset (QuerySet): The queryset used to retrieve traffic rules
            from the database.
            serializer_class (Serializer): The serializer class used to
            serialize traffic rules.

        Methods:
            get(request: Request) -> JsonResponse: Retrieves traffic rules from
            the database and returns them as a JSON response.
        """
        # Generates the result in required key value format from DB
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT json_object_agg(app_deployment_id , rule) AS "
                "result FROM public.traffic_routing_trafficrule"
            )
            traffic_rules = cursor.fetchone()[0]
        result = {"http": {"routers": traffic_rules}}
        # Return the dictionary as a JSON response
        return JsonResponse(result)

    def get_app_and_org(self, request: Request) -> JsonResponse:
        """Retrieve app details and organization details from global traffic
        rules and check user access.

        Args:
            request (Request): The request object.

        Returns:
            JsonResponse: A JSON response containing the app ID and
            organization ID.

        Raises:
            APINotFound: If the app is not found for the given host.
            Forbidden: If the user does not have access to the app organization.
        """
        host = request.get_host()
        Logger.info("Accessing app deployment at %s", host)
        if not host:
            Logger.error("App not found for host %s.", host)
            raise APINotFound("App not found.")
        try:
            #  Get app details and org details from global traffic rules
            routing_detail = TrafficRule.objects.get(fqdn=host)
            app_id = routing_detail.app_deployment_id
            app_organization = routing_detail.organization

            #  Check user in the org
            #  TODO: Organization details should be saved in session on login
            #  And the same should be used for this logic.
            auth_controller = AuthenticationController()
            organizations: list[
                OrganizationData
            ] = auth_controller.auth_service.get_organizations_by_user_id(
                request.user.user_id
            )
            app_organization_access = False
            for organization in organizations:
                if app_organization.organization_id == organization.id:
                    app_organization_access = True
                    break
            if not app_organization_access:
                Logger.error(
                    "Access forbidden: %s tried accessing %s using %s",
                    request.user,
                    app_id,
                    host,
                )
                raise Forbidden("Access denied.")
            result = {
                "app_id": app_id,
                "org_id": app_organization.organization_id,
            }
            return JsonResponse(result)
        except TrafficRule.DoesNotExist as e:
            Logger.error("App not found for host %s. Error: %s", host, e)
            raise APINotFound("App not found.")
