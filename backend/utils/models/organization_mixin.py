# TODO:V2 class
from account_v2.models import Organization
from django.db import models
from utils.constants import FeatureFlag
from utils.user_context import UserContext

from unstract.flags.feature_flag import check_feature_flag_status


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
        if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
            organization = UserContext.get_organization()
            return super().get_queryset().filter(organization=organization)
        return super().get_queryset()
