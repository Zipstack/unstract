import uuid

from account.models import User
from django.core.validators import RegexValidator
from django.db import models
from utils.models.base_model import BaseModel
from workflow_manager.workflow.models import Workflow

APPLICATION_NAME_MAX_LENGTH = 30
SUBDOMAIN_NAME_MAX_LENGTH = 30
DESCRIPTION_MAX_LENGTH = 255


class DNSProvider(models.TextChoices):
    """List of possible DNS providers.

    Attributes:
        LOCALHOST: Represents the Localhost DNS provider.
        CLOUDFLARE: Represents the Cloudflare DNS provider.
        TODO: Add GCP, AWS etc
    """

    LOCALHOST = "LOCALHOST", "Localhost DNS"
    CLOUDFLARE = "CLOUDFLARE", "Cloudflare DNS"


class AppDeployment(BaseModel):
    """App Deployment.

    Args:
        BaseModel (_type_): _description_
    """

    class TemplateType(models.TextChoices):
        """List of possible Template types.

        Args:
            models (_type_): _description_
        """

        CHAT = "CHAT", "Chat"
        QUESTIONS = "QUESTIONS", "Canned Questions"
        CHATANDQUESTIONS = "CHATANDQUESTIONS", "Chat with Canned Questions"

    class KBModeType(models.TextChoices):
        """List of possible Knowledge Base Mode types.

        Args:
            models (_type_): _description_
        """

        SINGLE = "SINGLE", "Single Document"
        MULTIPLE = "MULTIPLE", "Multiple Documents"

    domain_validators = RegexValidator(
        regex=r"^[a-zA-Z0-9.-]+$",
        message="Enter a valid domain name.",
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_name = models.CharField(
        max_length=APPLICATION_NAME_MAX_LENGTH,
        default="api deployment",
        db_comment="User-given name for the Application.",
    )
    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        null=True,
        db_comment="User-given description for the Application",
    )
    subdomain = models.CharField(
        max_length=SUBDOMAIN_NAME_MAX_LENGTH,
        unique=True,
        db_comment="User-given name for the Application.",
        validators=[domain_validators],
    )
    dns_domain = models.CharField(
        max_length=255,
        db_comment="Main domain under which the subdomain is added.",
        editable=False,
        validators=[domain_validators],
    )
    dns_top_level_domain = models.CharField(
        max_length=255,
        db_comment="Top domain like com, io etc.",
        editable=False,
        validators=[domain_validators],
    )
    dns_provider = models.CharField(
        choices=DNSProvider.choices,
        db_comment="DNS Provider which was used for configuration.",
        editable=False,
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        db_comment="Foreign key reference to Workflow model.",
    )
    template = models.CharField(choices=TemplateType.choices, default=TemplateType.CHAT)
    knowledge_base_mode = models.CharField(
        choices=KBModeType.choices, default=KBModeType.SINGLE
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating status is active or not.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="app_deployment_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="app_deployment_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
