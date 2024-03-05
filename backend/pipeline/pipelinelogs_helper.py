from typing import Any

from pipeline.models import Pipeline, PipelineLogs
from pipeline.pipeline_processor import PipelineProcessor


class PipelineLogsHelper:
    @staticmethod
    def fetch_execution_history(pipeline_id: str) -> Any:
        """Fetches the pipline execution history records belongs to the given
        pipeline_id.

        Args:
            pipeline_id (str): UUID of the pipeline record

        Returns:
            any: The pipeline logs
        """
        pipeline: Pipeline = PipelineProcessor.get_pipeline_by_id(pipeline_id)
        pipeline_logs: PipelineLogs = PipelineLogs.objects.filter(
            pipeline=pipeline
        )
        return pipeline_logs
