from typing import Any

import requests
from llama_index.core.callbacks import CBEventType, TokenCountingHandler

from unstract.sdk1.constants import LogLevel, ToolEnv
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.stream import StreamMixin
from unstract.sdk1.utils.token_counter import TokenCounter


class Audit(StreamMixin):
    """The 'Audit' class is responsible for pushing usage data to the platform
    service.

    Methods:
        - push_usage_data: Pushes the usage data to the platform service.

    Attributes:
        None
    """

    def __init__(self, log_level: LogLevel = LogLevel.INFO) -> None:
        super().__init__(log_level)

    def push_usage_data(
        self,
        platform_api_key: str,
        token_counter: TokenCountingHandler | TokenCounter = None,
        model_name: str = "",
        event_type: CBEventType = None,
        kwargs: dict[Any, Any] = None,
    ) -> None:
        """Pushes the usage data to the platform service.

        Args:
            platform_api_key (str): The platform API key.
            token_counter (TokenCountingHandler, optional): The token counter
                object. Defaults to None.
            model_name (str, optional): The name of the model.
                Defaults to "".
            event_type (CBEventType, optional): The type of the event. Defaults
                to None.
            **kwargs: Optional keyword arguments.
                workflow_id (str, optional): The ID of the workflow.
                    Defaults to "".
                execution_id (str, optional): The ID of the execution. Defaults
                    to "".
                adapter_instance_id (str, optional): The adapter instance ID.
                    Defaults to "".
                run_id (str, optional): The run ID. Defaults to "".

        Returns:
            None

        Raises:
            requests.RequestException: If there is an error while pushing the
            usage details.
        """
        platform_host = self.get_env_or_die(ToolEnv.PLATFORM_HOST)
        platform_port = self.get_env_or_die(ToolEnv.PLATFORM_PORT)

        base_url = PlatformHelper.get_platform_base_url(
            platform_host=platform_host, platform_port=platform_port
        )
        bearer_token = platform_api_key

        workflow_id = kwargs.get("workflow_id", "")
        execution_id = kwargs.get("execution_id", "")
        adapter_instance_id = kwargs.get("adapter_instance_id", "")
        run_id = kwargs.get("run_id", "")
        provider = kwargs.get("provider", "")
        llm_usage_reason = ""
        if event_type == "llm":
            llm_usage_reason = kwargs.get("llm_usage_reason", "")
        data = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "adapter_instance_id": adapter_instance_id,
            "run_id": run_id,
            "usage_type": event_type,
            "llm_usage_reason": llm_usage_reason,
            "model_name": model_name,
            "provider": provider,
            "embedding_tokens": token_counter.total_embedding_token_count,
            "prompt_tokens": token_counter.prompt_llm_token_count,
            "completion_tokens": token_counter.completion_llm_token_count,
            "total_tokens": token_counter.total_llm_token_count,
        }

        url = f"{base_url}/usage"
        headers = {"Authorization": f"Bearer {bearer_token}"}

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code != 200:
                self.stream_log(
                    log=(
                        "Error while pushing usage details: "
                        f"{response.status_code} {response.reason}",
                    ),
                    level=LogLevel.ERROR,
                )
            else:
                self.stream_log(
                    f"Successfully pushed usage details, {data}", level=LogLevel.DEBUG
                )

        except requests.RequestException as e:
            self.stream_log(
                log=f"Error while pushing usage details: {e}",
                level=LogLevel.ERROR,
            )

        finally:
            if isinstance(token_counter, TokenCountingHandler):
                token_counter.reset_counts()

    def push_page_usage_data(
        self,
        platform_api_key: str,
        page_count: int,
        file_size: int,
        file_type: str,
        kwargs: dict[Any, Any] = None,
    ) -> None:
        platform_host = self.get_env_or_die(ToolEnv.PLATFORM_HOST)
        platform_port = self.get_env_or_die(ToolEnv.PLATFORM_PORT)
        run_id = kwargs.get("run_id", "")
        file_name = kwargs.get("file_name", "")
        base_url = PlatformHelper.get_platform_base_url(
            platform_host=platform_host, platform_port=platform_port
        )
        bearer_token = platform_api_key
        url = f"{base_url}/page-usage"
        headers = {"Authorization": f"Bearer {bearer_token}"}

        data = {
            "page_count": page_count,
            "file_name": file_name,
            "file_size": file_size,
            "file_type": file_type,
            "run_id": run_id,
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code != 200:
                self.stream_log(
                    log=(
                        "Error while pushing page usage details: "
                        f"{response.status_code} {response.reason}",
                    ),
                    level=LogLevel.ERROR,
                )
            else:
                self.stream_log(
                    "Successfully pushed page usage details", level=LogLevel.DEBUG
                )

        except requests.RequestException as e:
            self.stream_log(
                log=f"Error while pushing page usage details: {e}",
                level=LogLevel.ERROR,
            )
