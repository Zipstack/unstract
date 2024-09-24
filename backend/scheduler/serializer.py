import logging
from typing import Any

from rest_framework import serializers
from scheduler.constants import SchedulerConstants as SC

from backend.constants import FeatureFlag
from backend.constants import FieldLengthConstants as FieldLength
from unstract.flags.feature_flag import check_feature_flag_status

if check_feature_flag_status(FeatureFlag.MULTI_TENANCY_V2):
    from pipeline_v2.manager import PipelineManager
else:
    from pipeline.manager import PipelineManager

logger = logging.getLogger(__name__)

JOB_NAME_LENGTH = 255


class JobKwargsSerializer(serializers.Serializer):
    verb = serializers.CharField(max_length=6)
    # TODO: Add custom URL field to allow URLs for running in docker
    # url = serializers.URLField()
    url = serializers.CharField(max_length=128)
    headers = serializers.JSONField()
    data = serializers.JSONField()


class AddJobSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=FieldLength.UUID_LENGTH)
    cron_string = serializers.CharField(
        max_length=FieldLength.CRON_LENGTH,
        allow_null=True,
        required=False,
        allow_blank=True,
    )
    name = serializers.CharField(
        max_length=JOB_NAME_LENGTH, required=False, allow_blank=True
    )
    job_kwargs = JobKwargsSerializer(write_only=True)

    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        if SC.NAME not in data:
            data[SC.NAME] = f"Job-{data[SC.ID]}"
        data[SC.JOB_KWARGS] = (
            PipelineManager.get_pipeline_execution_data_for_scheduled_run(
                pipeline_id=data[SC.ID]
            )
        )
        return super().to_internal_value(data)  # type: ignore
