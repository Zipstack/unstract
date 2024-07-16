import logging

from django.db import models

logger = logging.getLogger(__name__)


class ToolBaseJSONField(models.JSONField):
    def from_db_value(self, value, expression, connection):  # type: ignore
        metadata = super().from_db_value(value, expression, connection)
        return metadata


# TODO: Investigate if ToolBaseJSONField can replace the need for ToolPropertyJSONField,
#       ToolSpecJSONField, ToolVariablesJSONField, and ToolMetadataJSONField classes.


class ToolPropertyJSONField(ToolBaseJSONField, models.JSONField):
    pass


class ToolSpecJSONField(ToolBaseJSONField, models.JSONField):
    pass


class ToolVariablesJSONField(ToolBaseJSONField, models.JSONField):
    pass


class ToolMetadataJSONField(ToolBaseJSONField, models.JSONField):
    pass
