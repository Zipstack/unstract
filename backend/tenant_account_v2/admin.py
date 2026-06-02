from django.contrib import admin

from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
)

admin.site.register(OrganizationMember)
admin.site.register(OrganizationGroup)
admin.site.register(GroupMembership)
