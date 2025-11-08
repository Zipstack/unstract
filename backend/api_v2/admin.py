from django.contrib import admin

from .models import APIDeployment, APIKey, OrganizationRateLimit


@admin.register(OrganizationRateLimit)
class OrganizationRateLimitAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "concurrent_request_limit",
        "created_at",
        "modified_at",
    ]
    list_filter = ["created_at", "modified_at"]
    search_fields = ["organization__name", "organization__organization_id"]
    readonly_fields = ["created_at", "modified_at"]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "organization",
                    "concurrent_request_limit",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "modified_at"),
                "classes": ("collapse",),
            },
        ),
    )


admin.site.register([APIDeployment, APIKey])
