import logging
from typing import Any

import litellm
from llama_index.core.callbacks import CBEventType, TokenCountingHandler
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.embeddings import BaseEmbedding
from unstract.sdk1.constants import LogLevel
from unstract.sdk1.tool.stream import StreamMixin

logger = logging.getLogger(__name__)


class UsageHandler(StreamMixin, BaseCallbackHandler):
    """Handler for usage events in LLM or Embedding models.

    UsageHandler class is a subclass of BaseCallbackHandler and is responsible for
    handling usage events in the LLM or Embedding models. It provides methods for
    starting and ending traces, as well as handling event starts and ends.

    Attributes:
        - token_counter (TokenCountingHandler): The token counter object used
          to count tokens in the LLM or Embedding models.
        - embed_model (BaseEmbedding): The embedding model object.
        - workflow_id (str): The ID of the workflow.
        - execution_id (str): The ID of the execution.
        - event_starts_to_ignore (Optional[list[CBEventType]]): A list of event
          types to ignore at the start.
        - event_ends_to_ignore (Optional[list[CBEventType]]): A list of event
          types to ignore at the end.
        - verbose (bool): A flag indicating whether to print verbose output.
    """

    def __init__(
        self,
        platform_api_key: str,
        token_counter: TokenCountingHandler | None = None,
        embed_model: BaseEmbedding = None,
        event_starts_to_ignore: list[CBEventType] | None = None,
        event_ends_to_ignore: list[CBEventType] | None = None,
        verbose: bool = False,
        log_level: LogLevel = LogLevel.INFO,
        kwargs: dict[Any, Any] = None,
    ) -> None:
        """Initialize the UsageHandler for tracking usage events in LLM/Embedding models.

        Args:
            platform_api_key: API key for platform service communication
            token_counter: Token counting handler for tracking token usage
            embed_model: Embedding model instance for embedding operations
            event_starts_to_ignore: List of event types to ignore at start
            event_ends_to_ignore: List of event types to ignore at end
            verbose: Whether to enable verbose output
            log_level: Logging level for output
            kwargs: Additional keyword arguments for usage tracking
        """
        if kwargs is None:
            kwargs = {}
        self.kwargs = kwargs.copy()
        self._verbose = verbose
        self.token_counter = token_counter
        self.embed_model = embed_model
        self._pending_usage: list[dict] = []
        self.platform_api_key = platform_api_key
        super().__init__(
            log_level=log_level,  # StreamMixin's args
            event_starts_to_ignore=event_starts_to_ignore or [],
            event_ends_to_ignore=event_ends_to_ignore or [],
        )

    def start_trace(self, trace_id: str | None = None) -> None:
        return

    def end_trace(
        self,
        trace_id: str | None = None,
        trace_map: dict[str, list[str]] | None = None,
    ) -> None:
        return

    def on_event_start(
        self,
        event_type: CBEventType,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        parent_id: str = "",
        kwargs: dict[Any, Any] = None,
    ) -> str:
        if kwargs is None:
            kwargs = {}
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        kwargs: dict[Any, Any] = None,
    ) -> None:
        """Push the usage of Embedding to platform service."""
        if kwargs is None:
            kwargs = {}
        if (
            event_type == CBEventType.EMBEDDING
            and event_type not in self.event_ends_to_ignore
            and payload is not None
        ):
            if self.embed_model is None:
                return
            if self.token_counter is None:
                logger.warning(
                    "Embedding usage callback invoked without token_counter; "
                    "skipping usage record."
                )
                return
            model_name = self.embed_model.model_name
            embedding_tokens = self.token_counter.total_embedding_token_count
            self.stream_log(
                log=f"Recording embedding usage for model {model_name}",
                level=LogLevel.DEBUG,
            )

            try:
                prompt_cost, _ = litellm.cost_per_token(
                    model=model_name,
                    prompt_tokens=embedding_tokens,
                    completion_tokens=0,
                )
                cost = prompt_cost
            except Exception:
                logger.warning(
                    "Failed to compute embedding cost for model=%s; recording 0.0",
                    model_name,
                    exc_info=True,
                )
                cost = 0.0

            # Collapse multi-segment IDs (``bedrock/anthropic/claude``) to
            # the trailing segment to match legacy Audit semantics.
            display_model = model_name.rsplit("/", 1)[-1] if model_name else model_name

            self._pending_usage.append(
                {
                    "usage_type": "embedding",
                    "model_name": display_model,
                    "adapter_instance_id": self.kwargs.get("adapter_instance_id", ""),
                    # run_id lands in a UUIDField — "" fails the cast; keep None.
                    "run_id": self.kwargs.get("run_id") or None,
                    "execution_id": self.kwargs.get("execution_id", ""),
                    "embedding_tokens": embedding_tokens,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost_in_dollars": cost,
                    "status": "SUCCESS",
                }
            )
            self.token_counter.reset_counts()

    def flush_pending_usage(self) -> list[dict]:
        """Return and clear all pending usage records."""
        records = self._pending_usage
        self._pending_usage = []
        return records
