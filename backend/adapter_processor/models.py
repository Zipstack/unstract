import uuid
from typing import Any

from account.models import User
from django.db import models
from django.db.models import QuerySet
from unstract.adapters.enums import AdapterTypes
from utils.models.base_model import BaseModel

ADAPTER_NAME_SIZE = 128
VERSION_NAME_SIZE = 64
ADAPTER_ID_LENGTH = 128


class AdapterInstanceModelManager(models.Manager):
    def get_queryset(self) -> QuerySet[Any]:
        return super().get_queryset()

    def for_user(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(models.Q(created_by=user) | models.Q(shared_users=user))
            .distinct("id")
        )


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

    shared_users = models.ManyToManyField(User, related_name="shared_adapters")

    objects = AdapterInstanceModelManager()

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


class UserDefaultAdapter(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    default_llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="default_llm_adapter",
    )
    default_embedding_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="default_embedding_adapter",
    )
    default_vector_db_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="default_vector_db_adapter",
    )

    default_x2text_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="default_x2text_adapter",
    )
