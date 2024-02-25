import logging

from django.db import models

logger = logging.getLogger(__name__)


class ToolPropertyJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        metadata = super().from_db_value(value, expression, connection)
        return metadata


class ToolSpecJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        metadata = super().from_db_value(value, expression, connection)
        return metadata


class ToolVariablesJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        metadata = super().from_db_value(value, expression, connection)
        return metadata


class ToolMetadataJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        metadata = super().from_db_value(value, expression, connection)
        return metadata
