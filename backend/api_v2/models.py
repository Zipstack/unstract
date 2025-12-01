import logging
import uuid
from typing import Any

from account_v2.models import User
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from pipeline_v2.models import Pipeline
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from api_v2.constants import ApiExecution

logger = logging.getLogger(__name__)

API_NAME_MAX_LENGTH = 30
DESCRIPTION_MAX_LENGTH = 255
API_ENDPOINT_MAX_LENGTH = 255


class APIDeploymentModelManager(DefaultOrganizationManagerMixin, models.Manager):
    def for_user(self, user):
        """Filter API deployments that the user can access:
        - API deployments created by the user
        - API deployments shared with the user
        - API deployments shared with the entire organization
        """
        from django.db.models import Q

        return self.filter(
            Q(created_by=user)  # Owned by user
            | Q(shared_users=user)  # Shared with user
            | Q(shared_to_org=True)  # Shared to entire organization
        ).distinct()


class APIDeployment(DefaultOrganizationMixin, BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(
        max_length=API_NAME_MAX_LENGTH,
        default="default api",
        db_comment="User-given display name for the API.",
    )
    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        blank=True,
        default="",
        db_comment="User-given description for the API.",
    )
    workflow = models.ForeignKey(
        Workflow,
        on_delete=models.CASCADE,
        db_comment="Foreign key reference to the Workflow model.",
        related_name="apis",
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating whether the API is active or not.",
    )
    # TODO: Implement dynamic generation of API endpoints for API deployments
    # instead of persisting them in the database.
    api_endpoint = models.CharField(
        max_length=API_ENDPOINT_MAX_LENGTH,
        unique=True,
        editable=False,
        db_comment="URL endpoint for the API deployment.",
    )
    api_name = models.CharField(
        max_length=API_NAME_MAX_LENGTH,
        default=uuid.uuid4,
        db_comment="Short name for the API deployment.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="apis_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="apis_modified",
        null=True,
        blank=True,
        editable=False,
    )
    # Sharing fields
    shared_users = models.ManyToManyField(
        User, related_name="shared_api_deployments", blank=True
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Whether this API deployment is shared with the entire organization",
    )

    # Manager
    objects = APIDeploymentModelManager()

    @property
    def api_key_data(self):
        return {"api": self.id, "description": f"API Key for {self.api_name}"}

    def __str__(self) -> str:
        return f"{self.id} - {self.display_name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save hook to update api_endpoint and enforce constraints.

        Custom save hook for updating the 'api_endpoint' based on
        'api_name'. If the instance is being updated, it checks for
        changes in 'api_name' and adjusts 'api_endpoint'
        accordingly. If the instance is new, 'api_endpoint' is set
        based on 'api_name' and the current database schema.

        Also enforces one API deployment per workflow constraint for new deployments.
        """
        organization_id = UserContext.get_organization_identifier()

        # Update api_endpoint logic
        if self.pk is not None:
            try:
                original = APIDeployment.objects.get(pk=self.pk)
                if original.api_name != self.api_name:
                    self.api_endpoint = (
                        f"{ApiExecution.PATH}/{organization_id}/{self.api_name}/"
                    )
            except APIDeployment.DoesNotExist:
                self.api_endpoint = (
                    f"{ApiExecution.PATH}/{organization_id}/{self.api_name}/"
                )
        else:
            # New instance - set api_endpoint
            self.api_endpoint = f"{ApiExecution.PATH}/{organization_id}/{self.api_name}/"

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Api Deployment"
        verbose_name_plural = "Api Deployments"
        db_table = "api_deployment"
        constraints = [
            models.UniqueConstraint(
                fields=["api_name", "organization"],
                name="unique_api_name",
            ),
        ]


class OrganizationRateLimit(DefaultOrganizationMixin, BaseModel):
    """Model to store organization-specific API deployment rate limits."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    concurrent_request_limit = models.IntegerField(
        default=5,
        db_comment="Maximum number of concurrent API deployment requests allowed for this organization",
    )

    def __str__(self) -> str:
        return f"{self.organization} - Limit: {self.concurrent_request_limit}"

    def save(self, *args, **kwargs):
        """Save and automatically clear cache."""
        super().save(*args, **kwargs)
        self._clear_cache()

    def _clear_cache(self):
        """Clear cached limit for this organization."""
        from django.core.cache import cache

        from api_v2.rate_limit_constants import RateLimitKeys

        org_id = str(self.organization.organization_id)
        cache_key = RateLimitKeys.get_org_limit_cache_key(org_id)
        cache.delete(cache_key)
        logger.info(f"Cleared rate limit cache after save: org {org_id}")

    class Meta:
        verbose_name = "Organization Rate Limit"
        verbose_name_plural = "Organization Rate Limits"
        db_table = "organization_rate_limit"
        constraints = [
            models.UniqueConstraint(
                fields=["organization"],
                name="unique_org_rate_limit",
            ),
        ]


class APIKey(BaseModel):
    id = models.UUIDField(
        primary_key=True,
        editable=False,
        default=uuid.uuid4,
        db_comment="Unique identifier for the API key.",
    )
    api_key = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_comment="Actual key UUID.",
    )
    api = models.ForeignKey(
        APIDeployment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_comment="Foreign key reference to the APIDeployment model.",
        related_name="api_keys",
    )
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_comment="Foreign key reference to the Pipeline model.",
    )
    description = models.CharField(
        max_length=DESCRIPTION_MAX_LENGTH,
        null=True,
        db_comment="Description of the API key.",
    )
    is_active = models.BooleanField(
        default=True,
        db_comment="Flag indicating whether the API key is active or not.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_keys_created",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="api_keys_modified",
        null=True,
        blank=True,
        editable=False,
    )

    def __str__(self) -> str:
        if self.api:
            api_name = self.api.api_name
        elif self.pipeline:
            api_name = self.pipeline.pipeline_name
        else:
            api_name = None

        api_key = self.api_key if self.api_key else None

        return f"{api_name} - {self.id} - {api_key}"

    class Meta:
        verbose_name = "Api Deployment key"
        verbose_name_plural = "Api Deployment keys"
        db_table = "api_deployment_key"


# Signal handlers for OrganizationRateLimit
@receiver(post_delete, sender=OrganizationRateLimit)
def clear_org_rate_limit_cache_on_delete(sender, instance, **kwargs):
    """Clear cache when rate limit record is deleted."""
    from django.core.cache import cache

    from api_v2.rate_limit_constants import RateLimitKeys

    org_id = str(instance.organization.organization_id)
    cache_key = RateLimitKeys.get_org_limit_cache_key(org_id)
    cache.delete(cache_key)
    logger.info(f"Cleared rate limit cache after delete: org {org_id}")
