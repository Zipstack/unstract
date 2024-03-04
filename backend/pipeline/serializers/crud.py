import logging
from collections import OrderedDict
from typing import Any

from connector.connector_instance_helper import ConnectorInstanceHelper
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
from utils.serializer_utils import SerializerUtils
from workflow_manager.workflow.constants import WorkflowKey

from backend.serializers import AuditSerializer
from unstract.connectors.connectorkit import Connectorkit

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

    def _get_name_and_icon(
        self, connectors: list[Any], connector_id: Any
    ) -> Any:
        for obj in connectors:
            if obj["id"] == connector_id:
                return obj["name"], obj["icon"]
        return PC.NOT_CONFIGURED, None

    def _add_connector_data(
        self,
        repr: OrderedDict[str, Any],
        connector_instance_list: list[Any],
        connectors: list[Any],
    ) -> OrderedDict[str, Any]:
        """Adds connector Input/Output data.

        Args:
            sef (_type_): _description_
            repr (OrderedDict[str, Any]): _description_

        Returns:
            OrderedDict[str, Any]: _description_
        """
        for instance in connector_instance_list:
            if instance.connector_type == "INPUT":
                repr[PC.SOURCE_NAME], repr[PC.SOURCE_ICON] = (
                    self._get_name_and_icon(
                        connectors=connectors,
                        connector_id=instance.connector_id,
                    )
                )
            if instance.connector_type == "OUTPUT":
                repr[PC.DESTINATION_NAME], repr[PC.DESTINATION_ICON] = (
                    self._get_name_and_icon(
                        connectors=connectors,
                        connector_id=instance.connector_id,
                    )
                )
        return repr

    def to_representation(self, instance: Pipeline) -> OrderedDict[str, Any]:
        """To set Source, Destination & Agency for Pipelines."""
        repr: OrderedDict[str, Any] = super().to_representation(instance)

        connector_kit = Connectorkit()
        connectors = connector_kit.get_connectors_list()

        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            workflow = instance.workflow
            connector_instance_list = ConnectorInstanceHelper.get_input_output_connector_instances_by_workflow(  # noqa
                workflow.id
            )
            repr[PK.WORKFLOW_ID] = workflow.id
            repr[PK.WORKFLOW_NAME] = workflow.workflow_name
            repr = self._add_cron_summary(repr=repr)
            repr = self._add_connector_data(
                repr=repr,
                connector_instance_list=connector_instance_list,
                connectors=connectors,
            )

        return repr

    def get_connector_data(self, connector: ConnectorInstance, key: str) -> Any:
        return ConnectorProcessor.get_connector_data_with_key(
            connector.connector_id, key
        )
