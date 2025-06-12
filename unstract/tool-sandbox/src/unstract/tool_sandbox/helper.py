import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from requests import Response
from requests.exceptions import ConnectionError, RequestException

from unstract.core.file_execution_tracker import (
    FileExecutionData,
    FileExecutionStage,
    FileExecutionStageData,
    FileExecutionStageStatus,
    FileExecutionStatusTracker,
)
from unstract.core.network import HttpClient, HTTPMethod, get_retry_session
from unstract.core.runner.enum import ContainerStatus
from unstract.core.tool_execution_status import (
    ToolExecutionData,
    ToolExecutionStatus,
    ToolExecutionTracker,
)
from unstract.core.utilities import UnstractUtils
from unstract.tool_sandbox.constants import UnstractRunner
from unstract.tool_sandbox.dto import (
    RunnerContainerRunResponse,
    RunnerContainerRunStatus,
)

logger = logging.getLogger(__name__)

COMPLETED_FINAL_STATUSES = {
    ContainerStatus.EXITED.value,
    ContainerStatus.DEAD.value,
    ContainerStatus.ERROR.value,
    ContainerStatus.NOT_FOUND.value,
}


class ToolSanboxError(Exception):
    pass


class ToolSandboxHelper:
    def __init__(
        self,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        messaging_channel: str,
        environment_variables: dict[str, str],
    ) -> None:
        runner_host = os.environ.get("UNSTRACT_RUNNER_HOST")
        runner_port = os.environ.get("UNSTRACT_RUNNER_PORT")
        self.base_url = f"{runner_host}:{runner_port}{UnstractRunner.BASE_API_ENDPOINT}"
        self.organization_id = str(organization_id)
        self.workflow_id = str(workflow_id)
        self.execution_id = str(execution_id)
        self.envs = environment_variables
        self.messaging_channel = str(messaging_channel)
        self.timeout = int(os.getenv("UNSTRACT_RUNNER_API_TIMEOUT", 120))
        self.retry_count = int(os.getenv("UNSTRACT_RUNNER_API_RETRY_COUNT", 5))
        self.backoff_factor = int(os.getenv("UNSTRACT_RUNNER_API_BACKOFF_FACTOR", 3))

        self.session = get_retry_session(
            retry_count=self.retry_count,
            backoff_factor=self.backoff_factor,
            raise_on_status=False,
        )
        self.http_client = HttpClient(
            session=self.session, base_url=self.base_url, timeout=self.timeout
        )

    def convert_str_to_dict(self, data: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(data, str):
            output: dict[str, Any] = {}
            try:
                output = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
            return output
        return data

    def make_get_request(
        self, image_name: str, image_tag: str, endpoint: str
    ) -> dict[str, Any] | None:
        """Make unstract runner Get request.

        Args:
            image_name (str): _description_
            image_tag (str): _description_
            endpoint (str): _description_

        Returns:
            Optional[dict[str, Any]]: _description_
        """
        url = f"{self.base_url}{endpoint}"
        params = {"image_name": image_name, "image_tag": image_tag}
        response = requests.get(url, params=params)
        result: dict[str, Any] | None = None
        if response.status_code == 200:
            result = response.json()
        elif response.status_code == 404:
            logger.error(
                f"Error while calling tool {image_name}: "
                f"for tool instance status code {response.status_code}"
            )
        else:
            logger.error(
                f"Error while calling tool {image_name} reason: {response.reason}"
            )
        return result

    def poll_tool_status(
        self,
        file_execution_id: str,
        file_execution_data: FileExecutionData | None = None,
    ) -> RunnerContainerRunResponse | None:
        if not file_execution_data:
            file_execution_tracker = FileExecutionStatusTracker()
            file_execution_data = file_execution_tracker.get_data(
                execution_id=self.execution_id, file_execution_id=file_execution_id
            )

        # Configurable polling values
        max_wait_seconds = int(os.getenv("MAX_RUNNER_POLLING_WAIT_SECONDS", 60 * 60 * 3))
        interval_seconds = int(os.getenv("RUNNER_POLLING_INTERVAL_SECONDS", 2))
        start_time = datetime.now(UTC)
        end_time = start_time + timedelta(seconds=max_wait_seconds)
        response: RunnerContainerRunResponse | None = None

        while datetime.now(UTC) < end_time:
            status = self._check_tool_run_status(file_execution_data.tool_container_name)
            elapsed = (datetime.now(UTC) - start_time).total_seconds()
            logger.info(
                f"Tool status {status} for execution_id: {self.execution_id} and file_execution_id: {file_execution_id} - elapsed: {elapsed:.2f}s"
            )
            if status and status.get("status") in COMPLETED_FINAL_STATUSES:
                error = self._handle_tool_execution_status(
                    execution_id=self.execution_id,
                    file_execution_id=file_execution_id,
                    container_name=file_execution_data.tool_container_name,
                )
                if error:
                    response = self._create_run_response(
                        status=RunnerContainerRunStatus.ERROR,
                        error=error,
                    )
                    break
                response = self._create_run_response(
                    status=RunnerContainerRunStatus.SUCCESS,
                )
                break
            time.sleep(interval_seconds)

        if not response:
            logger.error(
                f"Tool {file_execution_data.tool_container_name} is not completed within {max_wait_seconds} seconds"
            )
            response = self._create_run_response(
                status=RunnerContainerRunStatus.ERROR,
                error=f"Tool is not completed within {max_wait_seconds} seconds",
            )

        if file_execution_data and file_execution_data.tool_container_name:
            self.cleanup_tool_container(
                container_name=file_execution_data.tool_container_name,
                file_execution_id=file_execution_id,
            )
        return response

    def call_tool_handler(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> RunnerContainerRunResponse | None:
        """Calling unstract runner to run the required tool.

        Args:
            image_name (str): image name
            image_tag (str): image tag
            params (dict[str, Any]): tool params
            settings (dict[str, Any]): tool settings

        Returns:
            Optional[dict[str, Any]]: tool response
        """
        file_execution_tracker = FileExecutionStatusTracker()
        file_execution_data = file_execution_tracker.get_data(
            execution_id=self.execution_id, file_execution_id=file_execution_id
        )

        if not file_execution_data:
            logger.warning(
                f"File execution data not found for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
            )
            file_execution_tracker.set_data(
                execution_id=self.execution_id,
                file_execution_id=file_execution_id,
                file_execution_data=FileExecutionData(
                    execution_id=self.execution_id,
                    file_execution_id=file_execution_id,
                    organization_id=self.organization_id,
                    stage_status=FileExecutionStageData(
                        stage=FileExecutionStage.INITIALIZATION,
                        status=FileExecutionStageStatus.SUCCESS,
                    ),
                    status_history=[],
                ),
            )
            response = self._run_and_poll(
                file_execution_id=file_execution_id,
                image_name=image_name,
                image_tag=image_tag,
                settings=settings,
                retry_count=retry_count,
            )

            self._update_stage_status_for_tool_execution(file_execution_id, response)
            self._update_stage_status(
                status=FileExecutionStageStatus.IN_PROGRESS,
                stage=FileExecutionStage.FINALIZATION,
                file_execution_id=file_execution_id,
            )
        else:
            logger.info(
                f"File execution data {file_execution_data} found for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
            )
            if file_execution_data.error:
                response = self._create_run_response(
                    status=RunnerContainerRunStatus.ERROR,
                    error=file_execution_data.error,
                )
                return response

            stage = file_execution_data.stage_status.stage
            logger.info(
                f"Current File execution stage {stage.value} for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
            )
            if stage == FileExecutionStage.TOOL_EXECUTION:
                response = self.poll_tool_status(
                    file_execution_id=file_execution_id,
                    file_execution_data=file_execution_data,
                )
                self._update_stage_status_for_tool_execution(file_execution_id, response)
                self._update_stage_status(
                    status=FileExecutionStageStatus.IN_PROGRESS,
                    stage=FileExecutionStage.FINALIZATION,
                    file_execution_id=file_execution_id,
                )
            elif stage.is_before(FileExecutionStage.TOOL_EXECUTION):
                self._update_stage_status(
                    status=FileExecutionStageStatus.SUCCESS,
                    stage=stage,
                    file_execution_id=file_execution_id,
                )
                response = self._run_and_poll(
                    file_execution_id=file_execution_id,
                    image_name=image_name,
                    image_tag=image_tag,
                    settings=settings,
                    retry_count=retry_count,
                )
                self._update_stage_status_for_tool_execution(file_execution_id, response)
                self._update_stage_status(
                    status=FileExecutionStageStatus.IN_PROGRESS,
                    stage=FileExecutionStage.FINALIZATION,
                    file_execution_id=file_execution_id,
                )
            else:
                logger.warning(
                    f"File execution data stage {file_execution_data.stage_status.stage} is after tool execution for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
                )
                # Assuming the tool execution is successful
                response = self._create_run_response(
                    status=RunnerContainerRunStatus.SUCCESS,
                )
        logger.info(
            f"Tool execution response: {response} for execution_id={self.execution_id}, file_execution_id={file_execution_id}"
        )
        return response

    def _run_and_poll(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> RunnerContainerRunResponse:
        logger.info(
            f"Calling runner to run tool container for execution_id={self.execution_id}, file_execution_id={file_execution_id}"
        )
        response = self.run_tool_container(
            file_execution_id=file_execution_id,
            image_name=image_name,
            image_tag=image_tag,
            settings=settings,
            retry_count=retry_count,
        )
        logger.info(
            f"Tool container run for execution_id={self.execution_id}, file_execution_id={file_execution_id} completed with status {response.status}"
        )

        if response.status == RunnerContainerRunStatus.RUNNING:
            logger.info(
                f"Polling tool container for execution_id={self.execution_id}, file_execution_id={file_execution_id}"
            )
            return self.poll_tool_status(file_execution_id)

        logger.info(
            f"Tool container run for execution_id={self.execution_id}, file_execution_id={file_execution_id} completed with status {response.status}"
        )
        return response

    def cleanup_tool_container(
        self,
        container_name: str,
        file_execution_id: str,
    ) -> None:
        headers = {
            "X-Request-ID": file_execution_id,
        }
        data = self.cleanup_tool_container_request_data(container_name=container_name)
        response = self.http_client(
            method=HTTPMethod.POST,
            endpoint=UnstractRunner.CLEANUP_TOOL_CONTAINER_API_ENDPOINT,
            headers=headers,
            json=data,
        )
        if response.status_code != 200:
            logger.error(
                f"Error while calling tool {container_name} reason: {response.reason}"
            )
        return response.json()

    def _update_stage_status(
        self,
        status: FileExecutionStageStatus,
        stage: FileExecutionStage,
        file_execution_id: str,
    ) -> None:
        file_execution_tracker = FileExecutionStatusTracker()

        file_execution_data = file_execution_tracker.get_data(
            execution_id=self.execution_id,
            file_execution_id=file_execution_id,
        )
        if not file_execution_data:
            logger.warning(
                f"File execution data not found for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
            )
            return
        if file_execution_data.stage_status.stage != stage:
            logger.warning(
                f"Existing file execution data stage {file_execution_data.stage_status.stage} is not {stage} for execution_id: {self.execution_id} and file_execution_id: {file_execution_id}"
            )
            return

        stage_status = file_execution_data.stage_status
        stage_status.status = status

        file_execution_tracker.update_stage_status(
            execution_id=self.execution_id,
            file_execution_id=file_execution_id,
            stage_status=stage_status,
        )

    def _update_stage_status_for_tool_execution(
        self,
        file_execution_id: str,
        response: RunnerContainerRunResponse,
    ) -> None:
        stage_status = (
            FileExecutionStageStatus.SUCCESS
            if response.status == RunnerContainerRunStatus.SUCCESS
            else FileExecutionStageStatus.FAILED
        )
        self._update_stage_status(
            status=stage_status,
            stage=FileExecutionStage.TOOL_EXECUTION,
            file_execution_id=file_execution_id,
        )

    def run_tool_container(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> RunnerContainerRunResponse | None:
        """Calling unstract runner to run the required tool.

        Args:
            image_name (str): image name
            image_tag (str): image tag
            params (dict[str, Any]): tool params
            settings (dict[str, Any]): tool settings

        Returns:
            Optional[dict[str, Any]]: tool response
        """
        headers = {
            "X-Request-ID": file_execution_id,
        }
        data = self.create_tool_request_data(
            file_execution_id, image_name, image_tag, settings, retry_count
        )

        response: Response = Response()
        try:
            response = self.http_client(
                method=HTTPMethod.POST,
                endpoint=UnstractRunner.RUN_API_ENDPOINT,
                headers=headers,
                json=data,
            )
            response.raise_for_status()
        except ConnectionError as connect_err:
            msg = "Unable to connect to unstract-runner."
            logger.error(f"{msg}\n{connect_err}")
            raise ToolSanboxError(msg) from connect_err
        except RequestException as e:
            error_message = str(e)
            content_type = response.headers.get("Content-Type", "").lower()
            if "application/json" in content_type:
                response_json = response.json()
                if "error" in response_json:
                    error_message = response_json["error"]
            elif response.text:
                error_message = response.text
            logger.error(f"Error from runner: {error_message}")
            raise ToolSanboxError(error_message) from e
        return RunnerContainerRunResponse.from_dict(response.json())

    def create_tool_request_data(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        container_name = UnstractUtils.build_tool_container_name(
            tool_image=image_name,
            tool_version=image_tag,
            file_execution_id=file_execution_id,
            retry_count=retry_count,
        )
        data = {
            "image_name": image_name,
            "image_tag": image_tag,
            "organization_id": self.organization_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "file_execution_id": file_execution_id,
            "container_name": container_name,
            "settings": settings,
            "envs": self.envs,
            "messaging_channel": self.messaging_channel,
        }
        return data

    def _create_run_response(
        self,
        status: RunnerContainerRunStatus = RunnerContainerRunStatus.SUCCESS,
        error: str | None = None,
    ) -> RunnerContainerRunResponse:
        return RunnerContainerRunResponse(
            type="RESULT",
            result=None,
            error=error,
            status=status,
        )

    def cleanup_tool_container_request_data(self, container_name: str) -> dict[str, Any]:
        """Creating cleanup tool container request data."""
        data = {"container_name": container_name}
        return data

    def _check_tool_run_status(
        self,
        container_name: str,
    ) -> dict[str, Any] | None:
        params = self._create_tool_run_status_check_request_data(container_name)
        response = self.http_client(
            method=HTTPMethod.GET,
            endpoint=UnstractRunner.RUN_STATUS_API_ENDPOINT,
            params=params,
        )
        result: dict[str, Any] | None = None
        if response.status_code == 200:
            result = response.json()
        else:
            logger.error(
                f"Error while calling tool {container_name} status code: {response.status_code} reason: {response.reason}"
            )
        return result

    def _create_tool_run_status_check_request_data(
        self,
        container_name: str,
    ) -> dict[str, Any]:
        params = {"container_name": container_name}
        return params

    def _handle_tool_execution_status(
        self, execution_id: str, file_execution_id: str, container_name: str
    ) -> str | None:
        """Get the tool execution status data from the tool execution tracker."""
        error = None
        tool_execution_data = ToolExecutionData(
            execution_id=execution_id,
            file_execution_id=file_execution_id,
        )
        tool_execution_tracker = ToolExecutionTracker()
        try:
            tool_execution_status_data = tool_execution_tracker.get_status(
                tool_execution_data
            )
            if not tool_execution_status_data:
                logger.warning(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} - failed to fetch execution status"
                )
                return error
            status = tool_execution_status_data.status
            error = tool_execution_status_data.error
            if status == ToolExecutionStatus.FAILED:
                logger.error(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} - tool run failed. Error: {error}"
                )
            elif status == ToolExecutionStatus.SUCCESS:
                logger.info(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} - tool execution completed successfully"
                )
            else:
                logger.warning(
                    f"Execution ID: {execution_id}, docker "
                    f"container: {container_name} - unexpected tool status: {status}"
                )
            return error
        except Exception as error:
            logger.error(
                f"Execution ID: {execution_id}, docker "
                f"container: {container_name} - failed to fetch execution status. Error: {error}",
                exc_info=True,
            )
            return str(error)
        finally:
            # Delete the status from cache since it is no longer needed
            # Note: Instead of deleting the status, we are updating the TTL to a lower value
            # to avoid deleting the status from cache when the file is still processing
            # TODO: Remove this if not required since it delete after completion
            tool_execution_tracker.update_ttl(
                tool_execution_data,
                ToolExecutionTracker.TOOL_EXECUTION_TRACKER_COMPLETED_TTL_IN_SECOND,
            )
