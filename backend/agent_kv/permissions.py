from platform_api.permissions import IsOrganizationAdmin as PlatformIsOrganizationAdmin


class IsOrganizationAdmin(PlatformIsOrganizationAdmin):
    message = "Only organization admins can manage Agent-KV API keys."


__all__ = ["IsOrganizationAdmin"]
