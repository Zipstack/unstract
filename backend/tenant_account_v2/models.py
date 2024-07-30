from account_v2.models import User
from django.db import models
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)


class OrganizationMemberModelManager(DefaultOrganizationManagerMixin, models.Manager):
    pass


class OrganizationMember(DefaultOrganizationMixin):
    member_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        default=None,
        related_name="organization_user",
    )
    role = models.CharField()
    is_login_onboarding_msg = models.BooleanField(
        default=True,
        db_comment="Flag to indicate whether the onboarding messages are shown",
    )
    is_prompt_studio_onboarding_msg = models.BooleanField(
        default=True,
        db_comment="Flag to indicate whether the prompt studio messages are shown",
    )

    def __str__(self):  # type: ignore
        return (
            f"OrganizationMember("
            f"{self.member_id}, role: {self.role}, user: {self.user})"
        )

    objects = OrganizationMemberModelManager()

    class Meta:
        db_table = "organization_member"
        verbose_name = "Organization Member"
        verbose_name_plural = "Organization Members"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="unique_organization_member",
            ),
        ]
