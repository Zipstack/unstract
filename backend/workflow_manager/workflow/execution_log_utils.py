import json
import logging
from datetime import datetime
from typing import Any

from account.models import Organization
from celery import shared_task
from django_tenants.utils import get_tenant_model, tenant_context
from unstract.workflow_execution.enums import LogType
from workflow_manager.workflow.models.execution_log import ExecutionLog

from unstract.core.constants import LogFieldName

logger = logging.getLogger(__name__)


def handle_received_log(sender, **kwargs):
    """Handle the received log from log signal.

    Args:
        sender (Any): The sender of the signal
        **kwargs (dict): The keyword arguments passed to the signal
    """
    data = kwargs.get("data")
    _store_log.delay(json_data=data)


@shared_task(
    name="store_logs",
    acks_late=True,
    autoretry_for=(Exception,),
    max_retries=1,
    retry_backoff=True,
    retry_backoff_max=500,
    retry_jitter=True,
)
def _store_log(json_data: Any) -> None:
    """Store the execution log in the database.

    This method is used to store the execution log in the database.
    It takes a JSON data as input and creates an ExecutionLog object with
    the provided data.
    Args:
        json_data (Any): The JSON data to be stored.
    Returns:
        None
    """
    if isinstance(json_data, bytes):
        # Decode byte-encoded JSON into a string
        json_data = json_data.decode("utf-8")

    if isinstance(json_data, str):
        try:
            # Parse the string as JSON
            json_data = json.loads(json_data)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON data {json_data}")
            return

    # Check if the data is a dictionary
    if not isinstance(json_data, dict):
        return

    # Extract required fields from the JSON data
    execution_id = json_data.get(LogFieldName.EXECUTION_ID)
    organization_id = json_data.get(LogFieldName.ORGANIZATION_ID)
    timestamp = json_data.get(LogFieldName.TIMESTAMP)
    log_type = json_data.get(LogFieldName.TYPE)

    # Check if all required fields are present
    if not all((execution_id, organization_id, timestamp, log_type)):
        return

    # Ensure the log type is "LOG"
    if log_type != LogType.LOG.value:
        return

    try:
        tenant: Organization = get_tenant_model().objects.get(
            schema_name=organization_id
        )
    except Organization.DoesNotExist:
        logger.error(f"Organization with ID {organization_id} does not exist.")
        return

    # Convert timestamp to datetime object
    event_time = datetime.fromtimestamp(timestamp)

    # Store the log data in the database within tenant context
    with tenant_context(tenant):
        ExecutionLog.objects.create(
            execution_id=execution_id,
            data=json_data,
            event_time=event_time,
        )


class ExecutionLogUtils:

    @staticmethod
    def get_execution_logs_by_execution_id(execution_id) -> list[ExecutionLog]:
        """Get all execution logs for a given execution ID.

        Args:
            execution_id (int): The ID of the execution.

        Returns:
            list[ExecutionLog]: A list of ExecutionLog objects.
        """
        return ExecutionLog.objects.filter(execution_id=execution_id)
