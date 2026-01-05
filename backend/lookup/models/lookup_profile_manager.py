"""LookupProfileManager model for managing adapter profiles in Look-Up projects."""

import uuid

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel

from lookup.exceptions import DefaultProfileError


class LookupProfileManager(BaseModel):
    """Model to store adapter configuration profiles for Look-Up projects.

    Each profile defines the set of adapters (X2Text, Embedding, VectorDB, LLM)
    to use for text extraction, indexing, and lookup operations.

    Follows the same pattern as Prompt Studio's ProfileManager.
    """

    profile_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    profile_name = models.TextField(
        blank=False, null=False, db_comment="Name of the profile"
    )

    # Foreign key to LookupProject
    lookup_project = models.ForeignKey(
        "LookupProject",
        on_delete=models.CASCADE,
        related_name="profiles",
        db_comment="Look-Up project this profile belongs to",
    )

    # Required Adapters - All must be configured
    vector_store = models.ForeignKey(
        AdapterInstance,
        db_comment="Vector database adapter for storing embeddings",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="lookup_profiles_vector_store",
    )

    embedding_model = models.ForeignKey(
        AdapterInstance,
        db_comment="Embedding model adapter for generating vectors",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="lookup_profiles_embedding_model",
    )

    llm = models.ForeignKey(
        AdapterInstance,
        db_comment="LLM adapter for query processing and response generation",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="lookup_profiles_llm",
    )

    x2text = models.ForeignKey(
        AdapterInstance,
        db_comment="X2Text adapter for extracting text from various file formats",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="lookup_profiles_x2text",
    )

    # Configuration fields
    chunk_size = models.IntegerField(
        default=1000,
        null=False,
        blank=False,
        db_comment="Size of text chunks for indexing",
    )

    chunk_overlap = models.IntegerField(
        default=200,
        null=False,
        blank=False,
        db_comment="Overlap between consecutive chunks",
    )

    similarity_top_k = models.IntegerField(
        default=5,
        null=False,
        blank=False,
        db_comment="Number of top similar chunks to retrieve",
    )

    # Flags
    is_default = models.BooleanField(
        default=False, db_comment="Whether this is the default profile for the project"
    )

    reindex = models.BooleanField(
        default=False, db_comment="Flag to trigger re-indexing of reference data"
    )

    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_profile_managers_created",
        null=True,
        blank=True,
        editable=False,
    )

    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="lookup_profile_managers_modified",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Lookup Profile Manager"
        verbose_name_plural = "Lookup Profile Managers"
        db_table = "lookup_profile_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["lookup_project", "profile_name"],
                name="unique_lookup_project_profile_name_index",
            ),
        ]

    def __str__(self):
        return f"{self.profile_name} ({self.lookup_project.name})"

    @staticmethod
    def get_default_profile(project):
        """Get the default profile for a Look-Up project.

        Args:
            project: LookupProject instance

        Returns:
            LookupProfileManager: The default profile

        Raises:
            DefaultProfileError: If no default profile exists
        """
        try:
            return LookupProfileManager.objects.get(
                lookup_project=project, is_default=True
            )
        except LookupProfileManager.DoesNotExist:
            raise DefaultProfileError(
                f"No default profile found for project {project.name}"
            )
