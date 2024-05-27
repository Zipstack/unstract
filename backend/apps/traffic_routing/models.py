"""Traffic Routing model."""

from account.models import Organization, User
from django.core.validators import RegexValidator
from django.db import models
from utils.models.base_model import BaseModel


class TrafficRule(BaseModel):
    """Rule class represents a model for traffic routing. This will be
    available in public schema. This will contain records of all active app
    deployments. This table can be used to find out app deployment id from the
    FQDN.

    Attributes:

        fqdn (str): The fully qualified domain name for the rule.
        app_deployment_id (UUID): The ID of the application deployment
                                  associated with the rule.
        rule (dict): The routing rule for the service.
        organization (Organization): The organization associated with the rule.
        created_by (User): The user who created the rule.
        modified_by (User): The user who last modified the rule.
    """

    fqdn_validator = RegexValidator(
        regex=r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        message="Enter a valid domain name.",
    )

    fqdn = models.CharField(
        max_length=255, primary_key=True, validators=[fqdn_validator]
    )
    app_deployment_id = models.UUIDField(editable=False)
    rule = models.JSONField(
        null=False,
        blank=False,
        default=dict,
        db_comment="Routing rule for the service",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        related_name="app_deployment_org",
        null=True,
        blank=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="traffic_rule_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="traffic_rule_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
