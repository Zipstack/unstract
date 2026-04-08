import logging
from typing import Any

import requests
from litellm import cost_per_token
from llama_index.core.callbacks import CBEventType, TokenCountingHandler
from unstract.sdk1.constants import LogLevel, ToolEnv
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.stream import StreamMixin
from unstract.sdk1.utils.common import TokenCounterCompat

logger = logging.getLogger(__name__)


class Audit(StreamMixin):
    """The 'Audit' class is responsible for pushing usage data to the platform service.

    Methods:
        - push_usage_data: Pushes the usage data to the platform service.

    Attributes:
        None
    """

    def __init__(self, log_level: LogLevel = LogLevel.INFO) -> None:
        """Initialize the Audit class for tracking usage data.

        Args:
            log_level: Logging level for output control
        """
        super().__init__(log_level)

    def push_usage_data(
        self,
        platform_api_key: str,
        token_counter: TokenCountingHandler | TokenCounterCompat = None,
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
        if kwargs is None:
            kwargs = {}
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

        prompt_tokens = token_counter.prompt_llm_token_count
        completion_tokens = token_counter.completion_llm_token_count
        input_tokens = prompt_tokens
        if event_type == "embedding":
            input_tokens = token_counter.total_embedding_token_count
            completion_tokens = 0

        # Compute cost using the full model name (e.g. "azure/gpt-4o")
        # before stripping the provider prefix for DB storage.
        cost_in_dollars = 0.0
        if model_name:
            try:
                prompt_cost, completion_cost = cost_per_token(
                    model=model_name,
                    prompt_tokens=input_tokens,
                    completion_tokens=completion_tokens,
                )
                cost_in_dollars = prompt_cost + completion_cost
            except Exception:
                logger.debug(
                    "Cost lookup failed for model %s, defaulting to 0", model_name
                )

        # Strip provider prefix for DB storage (e.g. "azure/gpt-4o" -> "gpt-4o")
        display_model_name = model_name.split("/", 1)[-1] if model_name else ""

        data = {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "adapter_instance_id": adapter_instance_id,
            "run_id": run_id,
            "usage_type": event_type,
            "llm_usage_reason": llm_usage_reason,
            "model_name": display_model_name,
            "provider": provider,
            "embedding_tokens": token_counter.total_embedding_token_count,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": token_counter.total_llm_token_count,
            "cost_in_dollars": cost_in_dollars,
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
        if kwargs is None:
            kwargs = {}
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
