from apps.app_deployment.models import AppDeployment
from rest_framework.serializers import (
    CharField,
    ModelSerializer,
    Serializer,
    SerializerMethodField,
)
from backend.serializers import AuditSerializer


class AppDeploymentListSerializer(ModelSerializer):
    """Serializer used for list API.

    Args:
        ModelSerializer (_type_): _description_
    """

    workflow_name = CharField(
        source="workflow.project.project_name", read_only=True
    )
    project_id = CharField(source="workflow.project_id", read_only=True)
    fqdn = SerializerMethodField("get_fqdn")

    class Meta:
        """_summary_"""

        model = AppDeployment
        fields = [
            "id",
            "workflow",
            "workflow_name",
            "project_id",
            "application_name",
            "description",
            "is_active",
            "subdomain",
            "dns_domain",
            "dns_top_level_domain",
            "fqdn",
            "template",
            "created_by",
        ]

    def get_fqdn(self, obj: AppDeployment) -> str:
        """Returns the fully qualified domain name (FQDN) of the application
        deployment.

        Args:
            obj (AppDeployment): An instance of the AppDeployment model
                                 representing an application deployment.

        Returns:
            str: A string representing the fully qualified domain name (FQDN)
                 of the application deployment.
        """
        return f"{obj.subdomain}.{obj.dns_domain}.{obj.dns_top_level_domain}"


class AppDeploymentSerializer(AuditSerializer):
    """Serializer used for Create API.

    Args:
        AuditSerializer (_type_): _description_
    """

    class Meta:
        """_summary_"""

        model = AppDeployment
        #  This will include all fields except the below.
        exclude = ["dns_domain", "dns_top_level_domain", "dns_provider"]


class AppDeploymentResponseSerializer(Serializer):
    """Serializer for create response.

    Args:
        Serializer (_type_): _description_
    """

    id = CharField()
