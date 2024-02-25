import uuid

from account.models import User
from django.db import models
from unstract.adapters.enums import AdapterTypes
from utils.models.base_model import BaseModel

ADAPTER_NAME_SIZE = 128
VERSION_NAME_SIZE = 64
ADAPTER_ID_LENGTH = 128


class AdapterInstance(BaseModel):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_comment="Unique identifier for the Adapter Instance",
    )
    adapter_name = models.TextField(
        max_length=ADAPTER_NAME_SIZE,
        null=False,
        blank=False,
        db_comment="Name of the Adapter Instance",
    )
    adapter_id = models.CharField(
        max_length=ADAPTER_ID_LENGTH,
        default="",
        db_comment="Unique identifier of the Adapter",
    )

    # TODO to be removed once the migration for encryption
    adapter_metadata = models.JSONField(
        db_column="adapter_metadata",
        null=False,
        blank=False,
        default=dict,
        db_comment="JSON adapter metadata submitted by the user",
    )
    adapter_metadata_b = models.BinaryField(null=True)
    adapter_type = models.CharField(
        choices=[(tag.value, tag.name) for tag in AdapterTypes],
        db_comment="Type of adapter LLM/EMBEDDING/VECTOR_DB",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="created_adapters",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="modified_adapters",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=False,
        db_comment="Is the adapter instance currently being used",
    )
    is_default = models.BooleanField(
        default=False,
        db_comment="Is the adapter instance default",
    )

    class Meta:
        verbose_name = "adapter_adapterinstance"
        verbose_name_plural = "adapter_adapterinstance"
        db_table = "adapter_adapterinstance"
        constraints = [
            models.UniqueConstraint(
                fields=["adapter_name", "adapter_type"],
                name="unique_adapter",
            ),
        ]
