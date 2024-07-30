import uuid

from django.db import models
from utils.models.base_model import BaseModel


class ExecutionLog(BaseModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    execution_id = models.UUIDField(
        editable=False,
        db_comment="Execution ID",
    )
    data = models.JSONField(db_comment="Execution log data")
    event_time = models.DateTimeField(db_comment="Execution log event time")

    def __str__(self):
        return f"Execution ID: {self.execution_id}, Message: {self.data}"

    class Meta:
        verbose_name = "Execution Log"
        verbose_name_plural = "Execution Logs"
        db_table = "execution_log"
