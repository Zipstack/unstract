from django.db import models


class BaseModel(models.Model):
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Creation timestamp (ISO 8601)"
    )
    modified_at = models.DateTimeField(
        auto_now=True, help_text="Last modification timestamp (ISO 8601)"
    )

    class Meta:
        abstract = True
