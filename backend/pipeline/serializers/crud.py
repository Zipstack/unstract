import logging
from collections import OrderedDict
from typing import Any

from backend.serializers import AuditSerializer
from connector.models import ConnectorInstance
from connector_processor.connector_processor import ConnectorProcessor
from cron_expression_generator.constants import CronKeys
from cron_expression_generator.descriptor import CronDescriptor
from cron_expression_generator.exceptions import CronDescriptionError
from pipeline.constants import PipelineConstants as PC
from pipeline.constants import PipelineKey as PK
from pipeline.models import Pipeline
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import UUIDField
from scheduler.helper import SchedulerHelper
from tool_instance.serializers import ToolInstanceSerializer
from tool_instance.tool_instance_helper import ToolInstanceHelper
from utils.serializer_utils import SerializerUtils
from workflow_manager.workflow.constants import WorkflowKey

logger = logging.getLogger(__name__)


class PipelineSerializer(AuditSerializer):
    workflow_id = UUIDField(write_only=True)

    class Meta:
        model = Pipeline
        fields = "__all__"
        extra_kwargs = {
            PK.WORKFLOW: {
                "required": False,
            },
        }

    def to_internal_value(self, data: dict[str, str]) -> OrderedDict[str, str]:
        if WorkflowKey.WF_ID in data:
            data[PK.WORKFLOW] = data[WorkflowKey.WF_ID]
        return super().to_internal_value(data)  # type: ignore

    def create(self, validated_data: dict[str, Any]) -> Any:
        # TODO: Deduce pipeline type based on WF?
        validated_data[PK.ACTIVE] = True  # Add this as default instead?
        validated_data[PK.SCHEDULED] = True
        return super().create(validated_data)

    def save(self, **kwargs: Any) -> Pipeline:
        pipeline: Pipeline = super().save(**kwargs)
        SchedulerHelper.add_job(
            str(pipeline.pk),
            cron_string=pipeline.cron_string,
        )
        return pipeline

    def validate_cron_string(self, value: str) -> str:
        try:
            CronDescriptor.describe_cron(value)
        except CronDescriptionError:
            raise ValidationError("Cron schedule is of invalid format")
        return value

    def _add_cron_summary(
        self, repr: OrderedDict[str, Any]
    ) -> OrderedDict[str, Any]:
        """Adds cron_summary in place if cron_string is present as a separate
        JSON.

        Args:
            repr (OrderedDict[str, Any]): Dict that has to be returned to
            the user

        Returns:
            OrderedDict[str, Any]: repr with the cron string and its summary
        """
        cron_string = repr.pop(CronKeys.CRON_STRING)
        if cron_string:
            repr[PK.CRON_DATA] = {
                CronKeys.CRON_STRING: cron_string,
                PK.CRON_SUMMARY: CronDescriptor.describe_cron(cron_string),
            }
        return repr

    def to_representation(self, instance: Pipeline) -> OrderedDict[str, Any]:
        """To set Source, Destination & Agency for Pipelines."""
        repr: OrderedDict[str, Any] = super().to_representation(instance)

        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            workflow = instance.workflow
            tool_instances = ToolInstanceSerializer(
                instance=ToolInstanceHelper.get_tool_instances_by_workflow(
                    workflow_id=instance.workflow_id, order_by="step"
                ),
                many=True,
                context=self.context,
            ).data
            repr[PK.WORKFLOW_ID] = workflow.id
            repr[PK.WORKFLOW_NAME] = workflow.workflow_name
            repr = self._add_cron_summary(repr=repr)

            if not tool_instances:
                repr[PC.SOURCE_NAME] = PC.SOURCE_NOT_CONFIGURED
                repr[PC.DESTINATION_NAME] = PC.DESTINATION_NOT_CONFIGURED
                return repr

            # TODO: Change here to handle pipeline src/dest based on WF
            repr[PC.DESTINATION_NAME] = PC.NOT_CONFIGURED

        return repr

    def get_connector_data(self, connector: ConnectorInstance, key: str) -> Any:
        return ConnectorProcessor.get_connector_data_with_key(
            connector.connector_id, key
        )
