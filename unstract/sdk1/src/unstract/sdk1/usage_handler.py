from typing import Any

from llama_index.core.callbacks import CBEventType, TokenCountingHandler
from llama_index.core.callbacks.base_handler import BaseCallbackHandler
from llama_index.core.callbacks.schema import EventPayload
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM

from unstract.sdk1.constants import LogLevel
from unstract.sdk1.tool.stream import StreamMixin
from unstract.sdk1.audit import Audit
from unstract.sdk1.utils.token_counter import TokenCounter


class UsageHandler(StreamMixin, BaseCallbackHandler):
    """UsageHandler class is a subclass of BaseCallbackHandler and is
    responsible for handling usage events in the LLM or Embedding models. It
    provides methods for starting and ending traces, as well as handling event
    starts and ends.

    Attributes:
        - token_counter (TokenCountingHandler): The token counter object used
          to count tokens in the LLM or Embedding models.
        - llm_model (LLM): The LLM model object.
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
        llm_model: LLM = None,
        embed_model: BaseEmbedding = None,
        event_starts_to_ignore: list[CBEventType] | None = None,
        event_ends_to_ignore: list[CBEventType] | None = None,
        verbose: bool = False,
        log_level: LogLevel = LogLevel.INFO,
        kwargs: dict[Any, Any] = None,
    ) -> None:
        self.kwargs = kwargs.copy()
        self._verbose = verbose
        self.token_counter = token_counter
        self.llm_model = llm_model
        self.embed_model = embed_model
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
        return event_id

    def on_event_end(
        self,
        event_type: CBEventType,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        kwargs: dict[Any, Any] = None,
    ) -> None:
        """Push the usage of  LLM or Embedding to platform service."""
        if (
            event_type == CBEventType.LLM
            and event_type not in self.event_ends_to_ignore
            and payload is not None
            and EventPayload.COMPLETION in payload
        ):
            model_name = self.llm_model.metadata.model_name
            # Need to push the data to via platform service
            self.stream_log(
                log=f"Pushing llm usage for model {model_name}", level=LogLevel.DEBUG
            )
            llm_token_counter: TokenCounter = TokenCounter.get_llm_token_counts(payload)
            Audit(log_level=self.log_level).push_usage_data(
                platform_api_key=self.platform_api_key,
                token_counter=llm_token_counter,
                event_type=event_type,
                model_name=self.llm_model.metadata.model_name,
                kwargs=self.kwargs,
            )

        elif (
            event_type == CBEventType.EMBEDDING
            and event_type not in self.event_ends_to_ignore
            and payload is not None
        ):
            model_name = self.embed_model.model_name
            # Need to push the data to via platform service
            self.stream_log(
                log=f"Pushing embedding usage for model {model_name}",
                level=LogLevel.DEBUG,
            )
            Audit(log_level=self.log_level).push_usage_data(
                platform_api_key=self.platform_api_key,
                token_counter=self.token_counter,
                event_type=event_type,
                model_name=self.embed_model.model_name,
                kwargs=self.kwargs,
            )
            self.token_counter.reset_counts()
