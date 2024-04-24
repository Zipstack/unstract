import uuid

from django.db import models
from utils.models.base_model import BaseModel


class Usage(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workflow_id = models.CharField(max_length=255)
    execution_id = models.CharField(max_length=255)
    adapter_instance_id = models.CharField(max_length=255)
    run_id = models.CharField(max_length=255)
    usage_type = models.CharField(max_length=255)
    model_type = models.CharField(max_length=255)
    embedding_tokens = models.IntegerField()
    prompt_tokens = models.IntegerField()
    completion_tokens = models.IntegerField()
    total_tokens = models.IntegerField()

    def __str__(self):
        return str(self.id)

    class Meta:
        db_table = "token_usage"
