import logging
from collections import OrderedDict
from typing import Any

from connector_processor.connector_processor import ConnectorProcessor
from connector_v2.models import ConnectorInstance
from croniter import croniter
from django.conf import settings
from pipeline_v2.constants import PipelineConstants as PC
from pipeline_v2.constants import PipelineKey as PK
from pipeline_v2.models import Pipeline
from rest_framework import serializers
from rest_framework.serializers import SerializerMethodField
from scheduler.helper import SchedulerHelper
from utils.serializer.integrity_error_mixin import IntegrityErrorMixin
from utils.serializer_utils import SerializerUtils
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

from backend.serializers import AuditSerializer
from unstract.connectors.connectorkit import Connectorkit

logger = logging.getLogger(__name__)
DEPLOYMENT_ENDPOINT = settings.API_DEPLOYMENT_PATH_PREFIX + "/pipeline"


class PipelineSerializer(IntegrityErrorMixin, AuditSerializer):
    api_endpoint = SerializerMethodField()

    class Meta:
        model = Pipeline
        fields = "__all__"

    unique_error_message_map: dict[str, dict[str, str]] = {
        "unique_pipeline_name": {
            "field": "pipeline_name",
            "message": (
                "This pipeline name is already in use. Please select a different name."
            ),
        },
        "unique_pipeline_entity": {
            "field": "pipeline_type",
            "message": ("Duplicate pipeline"),
        },
    }

    # Error message constants for cron validation
    _CRON_ERROR_EVERY_MINUTE = (
        "Cron schedule cannot run every minute. Please provide a "
        "cron schedule to run at 30-minute or less frequent intervals."
    )
    _CRON_ERROR_TOO_FREQUENT = (
        "Cron schedule cannot run more frequently than every 30 minutes. "
        "Please provide a cron schedule to run at 30-minute or less frequent intervals."
    )
    _CRON_ERROR_COMPLEX_PATTERN = (
        "Complex minute patterns are not supported for intervals shorter than 1 hour. "
        "For 30-minute intervals, use '0,30' format."
    )
    _CRON_ERROR_RANGE_PATTERN = (
        "Range minute patterns are not supported for intervals shorter than 1 hour. "
        "Please use simple minute values (0-59) for 30-minute or less frequent intervals."
    )

    def _validate_basic_cron_format(self, value: str | None) -> str | None:
        """Validate basic cron format and handle None/empty cases."""
        if value is None:
            return None
        
        cron_string = value.strip()
        if not cron_string:
            return None

        try:
            croniter(cron_string)
        except Exception as error:
            logger.error(f"Invalid cron string '{cron_string}': {error}")
            raise serializers.ValidationError("Invalid cron string format.")
        
        return cron_string

    def _validate_step_pattern(self, minute_field: str) -> None:
        """Validate step patterns like */15."""
        parts = minute_field.split("/")
        if len(parts) == 2 and parts[1].isdigit():
            step = int(parts[1])
            if step < 30:
                raise serializers.ValidationError(self._CRON_ERROR_TOO_FREQUENT)

    def _validate_comma_pattern(self, minute_field: str) -> None:
        """Validate comma patterns like 0,30."""
        parts = [p.strip() for p in minute_field.split(",")]
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            minutes = [int(p) for p in parts]
            if sorted(minutes) != [0, 30]:
                raise serializers.ValidationError(self._CRON_ERROR_COMPLEX_PATTERN)
        else:
            raise serializers.ValidationError(self._CRON_ERROR_COMPLEX_PATTERN)

    def _validate_range_pattern(self, minute_field: str) -> None:
        """Validate range patterns like 0-30."""
        raise serializers.ValidationError(self._CRON_ERROR_RANGE_PATTERN)

    def _validate_minute_field(self, minute_field: str) -> None:
        """Validate the minute field for 30-minute minimum intervals."""
        if minute_field == "*":
            raise serializers.ValidationError(self._CRON_ERROR_EVERY_MINUTE)

        if "/" in minute_field:
            self._validate_step_pattern(minute_field)
        elif "," in minute_field:
            self._validate_comma_pattern(minute_field)
        elif "-" in minute_field:
            self._validate_range_pattern(minute_field)

    def validate_cron_string(self, value: str | None = None) -> str | None:
        """Validate the cron string provided in the serializer data.

        This method is called internally by the serializer to ensure that
        the cron string is well-formed and adheres to the correct format.
        If the cron string is valid, it is returned. If the string is None
        or empty, it returns None. If the string is invalid, a
        ValidationError is raised.

        Args:
            value (Optional[str], optional): The cron string to validate.
                                             Defaults to None.

        Raises:
            serializers.ValidationError: Raised if the cron string is
                                         not in a valid format.

        Returns:
            Optional[str]: The validated cron string if it is valid,
                           otherwise None.
        """
        cron_string = self._validate_basic_cron_format(value)
        if cron_string is None:
            return None

        cron_parts = cron_string.split()
        minute_field = cron_parts[0]
        
        self._validate_minute_field(minute_field)
        
        return cron_string

    def get_api_endpoint(self, instance: Pipeline):
        """Retrieve the API endpoint URL for a given Pipeline instance.

        This method is an internal serializer call that fetches the
        `api_endpoint` property from the provided Pipeline instance.

        Args:
            instance (Pipeline): The Pipeline instance for which the API
                                 endpoint URL is being retrieved.

        Returns:
            str: The API endpoint URL associated with the Pipeline instance.
        """
        return instance.api_endpoint

    def create(self, validated_data: dict[str, Any]) -> Any:
        # TODO: Deduce pipeline type based on WF?
        validated_data[PK.ACTIVE] = True
        return super().create(validated_data)

    def save(self, **kwargs: Any) -> Pipeline:
        if PK.CRON_STRING in self.validated_data:
            if self.validated_data[PK.CRON_STRING]:
                self.validated_data[PK.SCHEDULED] = True
            else:
                self.validated_data[PK.SCHEDULED] = False
        pipeline: Pipeline = super().save(**kwargs)
        if pipeline.cron_string is None:
            SchedulerHelper.remove_job(pipeline_id=str(pipeline.id))
        else:
            SchedulerHelper.add_or_update_job(pipeline)
        return pipeline

    def _get_name_and_icon(self, connectors: list[Any], connector_id: Any) -> Any:
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
        repr[PC.SOURCE_NAME] = PC.NOT_CONFIGURED
        repr[PC.DESTINATION_NAME] = PC.NOT_CONFIGURED
        for instance in connector_instance_list:
            if instance.connector_type == "INPUT":
                repr[PC.SOURCE_NAME], repr[PC.SOURCE_ICON] = self._get_name_and_icon(
                    connectors=connectors,
                    connector_id=instance.connector_id,
                )
            if instance.connector_type == "OUTPUT":
                repr[PC.DESTINATION_NAME], repr[PC.DESTINATION_ICON] = (
                    self._get_name_and_icon(
                        connectors=connectors,
                        connector_id=instance.connector_id,
                    )
                )
            if repr[PC.DESTINATION_NAME] == PC.NOT_CONFIGURED:
                try:
                    check_manual_review = WorkflowEndpoint.objects.get(
                        workflow=instance.workflow,
                        endpoint_type=WorkflowEndpoint.EndpointType.DESTINATION,
                        connection_type=WorkflowEndpoint.ConnectionType.MANUALREVIEW,
                    )
                    if check_manual_review:
                        repr[PC.DESTINATION_NAME] = "Manual Review"
                except Exception as ex:
                    logger.debug(f"Not a Manual review destination: {ex}")
        return repr

    def to_representation(self, instance: Pipeline) -> OrderedDict[str, Any]:
        """To set Source, Destination & Agency for Pipelines."""
        repr: OrderedDict[str, Any] = super().to_representation(instance)

        connector_kit = Connectorkit()
        connectors = connector_kit.get_connectors_list()

        if SerializerUtils.check_context_for_GET_or_POST(context=self.context):
            workflow = instance.workflow
            connector_instance_list = ConnectorInstance.objects.filter(
                workflow=workflow.id
            ).all()
            repr[PK.WORKFLOW_ID] = workflow.id
            repr[PK.WORKFLOW_NAME] = workflow.workflow_name
            repr[PK.CRON_STRING] = repr.pop(PK.CRON_STRING)
            repr = self._add_connector_data(
                repr=repr,
                connector_instance_list=connector_instance_list,
                connectors=connectors,
            )

        return repr

    def get_connector_data(self, connector: ConnectorInstance, key: str) -> Any:
        return ConnectorProcessor.get_connector_data_with_key(connector.connector_id, key)
