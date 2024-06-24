import uuid
from django.db import models
from utils.models.base_model import BaseModel
from simple_prompt_studio.sps_project.models import SPSProject

class SPSDocument(BaseModel):
    class IndexStatus(models.TextChoices):
        YET_TO_START = 'yet_to_start', 'Yet to Start'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    document_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document_name = models.CharField(db_comment="Field to store document name", max_length=255, editable=True)
    tool = models.ForeignKey(SPSProject, on_delete=models.CASCADE, related_name="documents")
    index_status = models.CharField(
        max_length=20,
        choices=IndexStatus.choices,
        default=IndexStatus.YET_TO_START,
        db_comment="Field to store index status"
    )

    class Meta:
        db_table = 'sps_document'
        constraints = [
            models.UniqueConstraint(fields=['tool', 'document_name'], name='unique_document_name_per_project')
        ]
