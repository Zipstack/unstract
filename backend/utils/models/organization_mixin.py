# TODO:V2 class
from account_v2.models import Organization
from django.db import models
from utils.user_context import UserContext


class DefaultOrganizationMixin(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        db_comment="Foreign key reference to the Organization model.",
        null=True,
        blank=True,
        default=None,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.organization is None:
            self.organization = UserContext.get_organization()
        super().save(*args, **kwargs)


class DefaultOrganizationManagerMixin(models.Manager):
    def get_queryset(self):
        organization = UserContext.get_organization()
        return super().get_queryset().filter(organization=organization)
