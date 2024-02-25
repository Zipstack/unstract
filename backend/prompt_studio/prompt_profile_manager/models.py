import uuid

from account.models import User
from adapter_processor.models import AdapterInstance
from django.db import models
from utils.models.base_model import BaseModel


class ProfileManager(BaseModel):
    """Model to store the LLM Triad management details for Prompt."""

    class RetrievalStrategy(models.TextChoices):
        SIMPLE = "simple", "Simple retrieval"
        SUBQUESTION = "subquestion", "Subquestion from prompt"
        VECTOR = "vector+keyword", "Uses vector for retrieval"

    profile_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    profile_name = models.TextField(unique=True, blank=False)
    vector_store = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the chosen vector store.",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profile_manager_vector",
    )
    embedding_model = models.ForeignKey(
        AdapterInstance,
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profile_manager_embedding",
    )
    llm = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the LLM chosen by the user",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profile_manager_llm",
    )
    x2text = models.ForeignKey(
        AdapterInstance,
        db_comment="Field to store the X2Text Adapter chosen by the user",
        blank=False,
        null=False,
        on_delete=models.PROTECT,
        related_name="profile_manager_x2text",
    )
    chunk_size = models.IntegerField(null=True, blank=True)
    chunk_overlap = models.IntegerField(null=True, blank=True)
    reindex = models.BooleanField(default=False)
    retrieval_strategy = models.TextField(
        choices=RetrievalStrategy.choices,
        blank=True,
        db_comment="Field to store the retrieval strategy for prompts",
    )
    similarity_top_k = models.IntegerField(
        blank=True, null=True, db_comment="Field to store matching count"
    )
    section = models.TextField(
        blank=True, null=True, db_comment="Field to store limit to section"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="profile_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="profile_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
