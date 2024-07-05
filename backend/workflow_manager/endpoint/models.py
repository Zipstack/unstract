import uuid

from connector.models import ConnectorInstance
from django.db import models
from utils.models.base_model import BaseModel
from workflow_manager.workflow.models.workflow import Workflow


class WorkflowEndpoint(BaseModel):
    class EndpointType(models.TextChoices):
        SOURCE = "SOURCE", "Source connector"
        DESTINATION = "DESTINATION", "Destination Connector"

    class ConnectionType(models.TextChoices):
        FILESYSTEM = "FILESYSTEM", "FileSystem connector"
        DATABASE = "DATABASE", "Database Connector"
        API = "API", "API Connector"
        APPDEPLOYMENT = "APPDEPLOYMENT", "App Deployment"
        MANUALREVIEW = "MANUALREVIEW", "Manual Review Queue Connector"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        db_index=True,
        editable=False,
        db_comment="Foreign key from Workflow model",
    )
    endpoint_type = models.CharField(
        choices=EndpointType.choices,
        editable=False,
        db_comment="Endpoint type (source or destination)",
    )
    connection_type = models.CharField(
        choices=ConnectionType.choices,
        blank=True,
        db_comment="Connection type (Filesystem, Database, API or Manualreview)",
    )
    configuration = models.JSONField(
        blank=True, null=True, db_comment="Configuration in JSON format"
    )
    connector_instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
        db_comment="Foreign key from ConnectorInstance model",
    )

    class Meta:
        db_table = "workflow_endpoints"
        verbose_name = "Workflow Endpoint"
        verbose_name_plural = "Workflow Endpoints"
