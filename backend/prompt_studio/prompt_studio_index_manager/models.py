import uuid

from django.db import models
from account.models import User
from prompt_studio.prompt_studio_document_manager.models import DocumentManager
from prompt_studio.prompt_profile_manager.models import ProfileManager
from utils.models.base_model import BaseModel

class IndexManager(BaseModel):
    """Model to store the index details"""
    
    index_manager_id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    
    document_manager = models.ForeignKey(
        DocumentManager,
        on_delete=models.CASCADE,
        related_name="index_manager_linked_document",
        editable=False,
        null=False,
        blank=False,
    )
    
    raw_llm_profile = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="index_manager_linked_raw_llm_profile",
        editable=False,
        null=True,
        blank=True,
    )
    
    summarize_llm_profile = models.ForeignKey(
        ProfileManager,
        on_delete=models.SET_NULL,
        related_name="index_manager_linked_summarize_llm_profile",
        editable=False,
        null=True,
        blank=True,
    )
    
    raw_index_id = models.CharField(
        db_comment="Field to store the raw index id",
        editable=False,
        null=True,
        blank=True,
    )
    
    summarize_index_id = models.CharField(
        db_comment="Field to store the summarize index id",
        editable=False,
        null=True,
        blank=True,
    )
    
    is_active = models.BooleanField(default=True)
    
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_index_manager_created_by",
        null=True,
        blank=True,
        editable=False,
    )
    
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="prompt_index_manager_modified_by",
        null=True,
        blank=True,
        editable=False,
    )
    
    