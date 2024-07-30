import json
import logging
import uuid
from typing import Any

from account_v2.models import User
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.db.models import QuerySet
from tenant_account_v2.models import OrganizationMember
from unstract.adapters.adapterkit import Adapterkit
from unstract.adapters.enums import AdapterTypes
from unstract.adapters.exceptions import AdapterError
from utils.models.base_model import BaseModel
from utils.models.organization_mixin import (
    DefaultOrganizationManagerMixin,
    DefaultOrganizationMixin,
)

logger = logging.getLogger(__name__)

ADAPTER_NAME_SIZE = 128
VERSION_NAME_SIZE = 64
ADAPTER_ID_LENGTH = 128

logger = logging.getLogger(__name__)


class AdapterInstanceModelManager(DefaultOrganizationManagerMixin, models.Manager):
    def get_queryset(self) -> QuerySet[Any]:
        return super().get_queryset()

    def for_user(self, user: User) -> QuerySet[Any]:
        return (
            self.get_queryset()
            .filter(
                models.Q(created_by=user)
                | models.Q(shared_users=user)
                | models.Q(shared_to_org=True)
                | models.Q(is_friction_less=True)
            )
            .distinct("id")
        )


class AdapterInstance(DefaultOrganizationMixin, BaseModel):
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
        related_name="adapters_created",
        null=True,
        blank=True,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="adapters_modified",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=False,
        db_comment="Is the adapter instance currently being used",
    )
    shared_to_org = models.BooleanField(
        default=False,
        db_comment="Is the adapter shared to entire org",
    )

    is_friction_less = models.BooleanField(
        default=False,
        db_comment="Was the adapter created through frictionless onboarding",
    )

    # Can be used if the adapter usage gets exhausted
    # Can also be used in other possible scenarios in feature
    is_usable = models.BooleanField(
        default=True,
        db_comment="Is the Adpater Usable",
    )

    # Introduced field to establish M2M relation between users and adapters.
    # This will introduce intermediary table which relates both the models.
    shared_users = models.ManyToManyField(User, related_name="shared_adapters_instance")
    description = models.TextField(blank=True, null=True, default=None)

    objects = AdapterInstanceModelManager()

    class Meta:
        verbose_name = "adapter instance"
        verbose_name_plural = "adapter instances"
        db_table = "adapter_instance"
        constraints = [
            models.UniqueConstraint(
                fields=["adapter_name", "adapter_type", "organization"],
                name="unique_organization_adapter",
            ),
        ]

    def create_adapter(self) -> None:

        encryption_secret: str = settings.ENCRYPTION_KEY
        f: Fernet = Fernet(encryption_secret.encode("utf-8"))

        self.adapter_metadata_b = f.encrypt(
            json.dumps(self.adapter_metadata).encode("utf-8")
        )
        self.adapter_metadata = {}

        self.save()

    def get_adapter_meta_data(self) -> Any:
        encryption_secret: str = settings.ENCRYPTION_KEY
        f: Fernet = Fernet(encryption_secret.encode("utf-8"))

        adapter_metadata = json.loads(
            f.decrypt(bytes(self.adapter_metadata_b).decode("utf-8"))
        )
        return adapter_metadata

    def get_context_window_size(self) -> int:

        adapter_metadata = self.get_adapter_meta_data()
        # Get the adapter_instance
        adapter_class = Adapterkit().get_adapter_class_by_adapter_id(self.adapter_id)
        try:
            adapter_instance = adapter_class(adapter_metadata)
            return adapter_instance.get_context_window_size()
        except AdapterError as e:
            logger.warning(f"Unable to retrieve context window size - {e}")
        return 0


class UserDefaultAdapter(BaseModel):
    organization_member = models.OneToOneField(
        OrganizationMember,
        on_delete=models.CASCADE,
        default=None,
        null=True,
        db_comment="Foreign key reference to the OrganizationMember model.",
        related_name="default_adapters",
    )
    default_llm_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="user_default_llm_adapter",
    )
    default_embedding_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="user_default_embedding_adapter",
    )
    default_vector_db_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="user_default_vector_db_adapter",
    )

    default_x2text_adapter = models.ForeignKey(
        AdapterInstance,
        on_delete=models.SET_NULL,
        null=True,
        related_name="user_default_x2text_adapter",
    )

    class Meta:
        verbose_name = "Default Adapter for Organization User"
        verbose_name_plural = "Default Adapters for Organization Users"
        db_table = "default_organization_user_adapter"
