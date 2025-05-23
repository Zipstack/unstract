import json
import uuid

from account_v2.models import Organization
from django.db import models
from utils.models.base_model import BaseModel

from configuration.enums import ConfigKey


class Configuration(BaseModel):
    """Model to hold details of Organization configs."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="organization_configuration"
    )
    key = models.CharField(max_length=100)
    value = models.TextField()
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Configuration"
        verbose_name_plural = "Configurations"
        db_table = "configuration"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key"],
                name="unique_organization_key",
            ),
        ]

    @property
    def typed_value(self):
        try:
            spec = ConfigKey[self.key].cast_value(self.value)
            return spec
        except ValueError:
            return None

    @classmethod
    def get_value_by_organization(
        cls, config_key: ConfigKey, organization: Organization | None = None
    ):
        if not organization:
            return config_key.value.default

        try:
            config = cls.objects.get(organization=organization, key=config_key.name)
            if not config.enabled:
                return config_key.value.default
            return config.typed_value
        except cls.DoesNotExist:
            return config_key.value.default
        except (ValueError, json.JSONDecodeError):
            return config_key.value.default
