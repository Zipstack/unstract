import logging
import os
import re
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NoReturn, cast

import litellm

# from litellm import get_supported_openai_params
from litellm import get_max_tokens, token_counter
from pydantic import ValidationError
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.audit import Audit
from unstract.sdk1.constants import Common as SdkCommon
from unstract.sdk1.constants import ToolEnv
from unstract.sdk1.exceptions import LLMError, SdkError, strip_litellm_prefix
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.common import (
    LLMResponseCompat,
    TokenCounterCompat,
    capture_metrics,
)

logger = logging.getLogger(__name__)

# Drop unsupported params rather than raising errors.
# Set once at module level instead of per-call to avoid repeated
# global mutation in concurrent environments.
litellm.drop_params = True


# ── Emulated llama-index types ───────────────────────────────────────────────
# These types emulate the llama-index interface without requiring the dependency.
# This allows LLMCompat to work with llama-index components like
# SubQuestionQueryEngine, QueryFusionRetriever, etc.


class MessageRole(str, Enum):
    """Emulates llama_index.core.base.llms.types.MessageRole."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"
    TOOL = "tool"


@dataclass
class ChatMessage:
    """Emulates llama_index.core.base.llms.types.ChatMessage."""

    role: MessageRole = MessageRole.USER
    content: str | None = None
    additional_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Emulates llama_index.core.base.llms.types.ChatResponse."""

    message: ChatMessage = field(default_factory=ChatMessage)
    raw: Any = None
    delta: str | None = None
    additional_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Emulates llama_index.core.base.llms.types.CompletionResponse."""

    text: str = ""
    raw: Any = None
    delta: str | None = None
    additional_kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMetadata:
    """Emulates llama_index.core.base.llms.types.LLMMetadata."""

    context_window: int = 4096
    num_output: int = 256
    is_chat_model: bool = True
    is_function_calling_model: bool = False
    model_name: str = ""
    system_role: MessageRole = MessageRole.SYSTEM


class LLM:
    """Unified LLM interface powered by LiteLLM.

    Internally invokes Unstract LLM adapters.

    Accepts either of the following pairs for init:
    - adapter ID and metadata       (e.g. test connection)
    - adapter instance ID and tool  (e.g. edit adapter)
    """

    SYSTEM_PROMPT = "You are a helpful assistant."
    MAX_TOKENS = 4096
    JSON_REGEX = re.compile(r"\[(?:.|\n)*\]|\{(?:.|\n)*\}")
    JSON_CONTENT_MARKER = os.environ.get("JSON_SELECTION_MARKER", "§§§")

    def __init__(  # noqa: C901
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, object] | None = None,
        adapter_instance_id: str = "",
        tool: BaseTool | None = None,
        usage_kwargs: dict[str, object] | None = None,
        system_prompt: str = "",
        kwargs: dict[str, object] | None = None,
        capture_metrics: bool = False,
    ) -> None:
        """Initialize the LLM interface.

        Args:
            adapter_id: Adapter identifier for LLM model
            adapter_metadata: Configuration metadata for the adapter
            adapter_instance_id: Instance identifier for the adapter
            tool: BaseTool instance for tool-specific operations
            usage_kwargs: Usage tracking parameters
            system_prompt: System prompt for the LLM
            kwargs: Additional keyword arguments for configuration
            capture_metrics: Whether to capture performance metrics
        """
        if adapter_metadata is None:
            adapter_metadata = {}
        if usage_kwargs is None:
            usage_kwargs = {}
        if kwargs is None:
            kwargs = {}
        self._usage_kwargs = usage_kwargs
        self._capture_metrics = capture_metrics
        try:
            llm_config = None

            if adapter_instance_id:
                if not tool:
                    raise SdkError(
                        "Broken LLM adapter tool binding: " + adapter_instance_id
                    )
                llm_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)

            if llm_config:
                self._adapter_id = llm_config[Common.ADAPTER_ID]
                self._adapter_metadata = llm_config[Common.ADAPTER_METADATA]
                self._adapter_instance_id = adapter_instance_id
                self._adapter_name = llm_config.pop(SdkCommon.ADAPTER_NAME, "")
                self._tool = tool
            else:
                self._adapter_id = adapter_id
                if adapter_metadata:
                    self._adapter_metadata = adapter_metadata
                else:
                    self._adapter_metadata = adapters[self._adapter_id][Common.METADATA]
                self._adapter_instance_id = ""
                self._adapter_name = ""
                self._tool = None

            # Retrieve the adapter class.
            self.adapter = adapters[self._adapter_id][Common.MODULE]
        except KeyError as e:
            raise SdkError(
                f"LLM adapter not supported: {adapter_id or adapter_instance_id}"
            ) from e

        try:
            self.platform_kwargs = {**kwargs, **usage_kwargs}

            if self._adapter_instance_id:
                self.platform_kwargs["adapter_instance_id"] = self._adapter_instance_id

            self.kwargs = self.adapter.validate(self._adapter_metadata)
            self._cost_model = self.kwargs.pop("cost_model", None)

            # REF: https://docs.litellm.ai/docs/completion/input#translated-openai-params
            # supported = get_supported_openai_params(model=self.kwargs["model"],
            #     custom_llm_provider=self.provider)
            # for s in supported:
            #     if s not in self.kwargs:
            #         logger.warning("Missing supported parameter for '%s': %s",
            #             self.adapter.get_provider(), s)
        except ValidationError as e:
            raise SdkError("Invalid LLM adapter metadata: " + str(e)) from e

        self._system_prompt = system_prompt or self.SYSTEM_PROMPT

        if self._tool:
            self._platform_api_key = self._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
            if not self._platform_api_key:
                raise SdkError(f"Missing env variable '{ToolEnv.PLATFORM_API_KEY}'")
        else:
            self._platform_api_key = os.environ.get(ToolEnv.PLATFORM_API_KEY, "")

        # Metrics capture.
        self._run_id = self.platform_kwargs.get("run_id")
        # Only override capture_metrics if it's explicitly set in platform_kwargs
        capture_metrics_from_platform = self.platform_kwargs.get("capture_metrics")
        if capture_metrics_from_platform is not None:
            self._capture_metrics = capture_metrics_from_platform
        self._metrics: dict[str, object] = {}

    def _get_adapter_info(self) -> str:
        """Build a display string identifying this adapter for errors."""
        provider = self.adapter.get_provider()
        if self._adapter_name:
            return f"{self._adapter_name} ({provider})"
        return provider

    def test_connection(self) -> bool:
        """Test connection to the LLM provider."""
        try:
            response = self.complete("What is the capital of Tamilnadu?")
            text = response["response"].text

            find_match = re.search("chennai", text.lower())
            if find_match:
                return True

            logger.error("LLM test response: %s", text)
            msg = (
                "LLM based test failed. The credentials was valid however a sane "
                "response was not obtained from the LLM provider, please recheck "
                "the configuration."
            )
            raise LLMError(message=msg, status_code=400)
        except LLMError:
            # Already wrapped in LLMError from complete(), re-raise as is
            raise
        except SdkError:
            # Already wrapped in SdkError, re-raise as is
            raise
        except Exception as e:
            # Catch any unexpected exceptions and wrap them
            logger.error("Failed to test connection for LLM: %s", e)

            # Extract status code if available
            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code
            elif hasattr(e, "http_status"):
                status_code = e.http_status

            # Wrap in LLMError with context
            raise LLMError(
                message=f"Failed to test LLM connection: {str(e)}",
                status_code=status_code,
                actual_err=e,
            ) from e

    @capture_metrics
    def complete(self, prompt: str, **kwargs: object) -> dict[str, object]:
        """Return a standard chat completion dict with optional metrics capture.

        Return a standard chat completion dict and optionally captures metrics if run
        ID is provided.

        Args:
            prompt   (str)   The input text prompt for generating the completion.
            **kwargs (Any)   Additional arguments passed to the completion function.

        Returns:
            dict[str, Any]  : A dictionary containing the result of the completion,
                any processed output, and the captured metrics (if applicable).
        """
        try:
            messages: list[dict[str, str]] = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ]
            logger.debug(
                f"[sdk1][LLM]Invoking {self.adapter.get_provider()} completion API"
            )

            completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})
            completion_kwargs.pop("cost_model", None)

            # if hasattr(self, "model") and self.model not in O1_MODELS:
            #     completion_kwargs["temperature"] = 0.003
            # if hasattr(self, "thinking_dict") and self.thinking_dict is not None:
            #     completion_kwargs["temperature"] = 1

            response: dict[str, object] = litellm.completion(
                messages=messages,
                **completion_kwargs,
            )

            response_text = response["choices"][0]["message"]["content"]
            finish_reason = response["choices"][0].get("finish_reason")

            self._record_usage(
                self._cost_model or self.kwargs["model"],
                messages,
                response.get("usage"),
                "complete",
            )

            # Handle refusal or empty content from the LLM provider
            if response_text is None:
                self._raise_for_empty_response(finish_reason)

            # NOTE:
            # The typecasting was required to stop the type checker from complaining.
            # Improvements in readability are definitely welcome.
            extract_json: bool = cast("bool", kwargs.get("extract_json", False))
            post_process_fn: (
                Callable[[LLMResponseCompat, bool, str], dict[str, object]] | None
            ) = cast(
                "Callable[[LLMResponseCompat, bool, str], dict[str, object]] | None",
                kwargs.get("process_text", None),
            )

            response_text, post_processed_output = self._post_process_response(
                response_text, extract_json, post_process_fn
            )

            response_object = LLMResponseCompat(response_text)
            response_object.raw = (
                response  # Attach raw litellm response for metadata access
            )
            return {"response": response_object, **post_processed_output}

        except LLMError:
            # Already wrapped LLMError, re-raise as is
            raise
        except SdkError:
            # Already wrapped SdkError, re-raise as is
            raise
        except Exception as e:
            # Wrap all other exceptions in LLMError with provider context
            logger.error(f"[sdk1][LLM] Error during completion: {e}")

            # Extract status code if available
            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code
            elif hasattr(e, "http_status"):
                status_code = e.http_status

            error_msg = (
                f"Error from LLM adapter '{self._get_adapter_info()}': "
                f"{strip_litellm_prefix(str(e))}"
            )

            raise LLMError(
                message=error_msg, status_code=status_code, actual_err=e
            ) from e

    def stream_complete(
        self,
        prompt: str,
        callback_manager: object | None = None,
        **kwargs: object,
    ) -> Generator[LLMResponseCompat, None, None]:
        """Yield LLMResponseCompat objects with text chunks.

        Chunks arrive as they stream from the provider.
        """
        try:
            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ]
            logger.debug(
                f"[sdk1][LLM]Invoking {self.adapter.get_provider()} stream completion API"
            )

            completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})
            completion_kwargs.pop("cost_model", None)

            has_yielded_content = False
            for chunk in litellm.completion(
                messages=messages,
                stream=True,
                stream_options={
                    "include_usage": True,
                },
                **completion_kwargs,
            ):
                if chunk.get("usage"):
                    self._record_usage(
                        self._cost_model or self.kwargs["model"],
                        messages,
                        chunk.get("usage"),
                        "stream_complete",
                    )

                response = self._process_stream_chunk(
                    chunk, callback_manager, has_yielded_content
                )
                if response is not None:
                    has_yielded_content = True
                    yield response

        except LLMError:
            # Already wrapped LLMError, re-raise as is
            raise
        except SdkError:
            # Already wrapped SdkError, re-raise as is
            raise
        except Exception as e:
            # Wrap all other exceptions in LLMError with provider context
            logger.error(f"[sdk1][LLM] Error during stream completion: {e}")

            # Extract status code if available
            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code
            elif hasattr(e, "http_status"):
                status_code = e.http_status

            error_msg = (
                f"Error from LLM adapter '{self._get_adapter_info()}': "
                f"{strip_litellm_prefix(str(e))}"
            )

            raise LLMError(
                message=error_msg, status_code=status_code, actual_err=e
            ) from e

    async def acomplete(self, prompt: str, **kwargs: object) -> dict[str, object]:
        """Asynchronous chat completion (wrapper around ``litellm.acompletion``)."""
        try:
            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ]
            logger.debug(
                f"[sdk1][LLM]Invoking {self.adapter.get_provider()} async completion API"
            )

            completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})
            completion_kwargs.pop("cost_model", None)

            response = await litellm.acompletion(
                messages=messages,
                **completion_kwargs,
            )
            response_text = response["choices"][0]["message"]["content"]
            finish_reason = response["choices"][0].get("finish_reason")

            self._record_usage(
                self._cost_model or self.kwargs["model"],
                messages,
                response.get("usage"),
                "acomplete",
            )

            # Handle refusal or empty content from the LLM provider
            if response_text is None:
                self._raise_for_empty_response(finish_reason)

            response_object = LLMResponseCompat(response_text)
            response_object.raw = (
                response  # Attach raw litellm response for metadata access
            )
            return {"response": response_object}

        except LLMError:
            # Already wrapped LLMError, re-raise as is
            raise
        except SdkError:
            # Already wrapped SdkError, re-raise as is
            raise
        except Exception as e:
            # Wrap all other exceptions in LLMError with provider context
            logger.error(f"[sdk1][LLM] Error during async completion: {e}")

            # Extract status code if available
            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code
            elif hasattr(e, "http_status"):
                status_code = e.http_status

            error_msg = (
                f"Error from LLM adapter '{self._get_adapter_info()}': "
                f"{strip_litellm_prefix(str(e))}"
            )

            raise LLMError(
                message=error_msg, status_code=status_code, actual_err=e
            ) from e

    @classmethod
    def get_context_window_size(
        cls, adapter_id: str, adapter_metadata: dict[str, object]
    ) -> int:
        """Returns the context window size of the LLM."""
        try:
            model = adapters[adapter_id][Common.MODULE].validate_model(adapter_metadata)
            return get_max_tokens(model)
        except Exception as e:
            logger.warning(f"Failed to get context window size for {adapter_id}: {e}")
            return cls.MAX_TOKENS

    @classmethod
    def get_max_tokens(
        cls, adapter_instance_id: str, tool: BaseTool, reserved_for_output: int = 0
    ) -> int:
        """Returns the maximum number of tokens limit for the LLM."""
        try:
            llm_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)
            adapter_id = llm_config[Common.ADAPTER_ID]
            adapter_metadata = llm_config[Common.ADAPTER_METADATA]

            model = adapters[adapter_id][Common.MODULE].validate_model(adapter_metadata)

            return get_max_tokens(model) - reserved_for_output
        except Exception as e:
            logger.warning(
                f"Failed to get context window size for {adapter_instance_id}: {e}"
            )
            return cls.MAX_TOKENS - reserved_for_output

    def get_model_name(self) -> str:
        """Gets the name of the LLM model.

        Returns:
            LLM model name
        """
        return self.kwargs["model"]

    def get_metrics(self) -> dict[str, object]:
        return self._metrics

    def get_usage_reason(self) -> object:
        return self.platform_kwargs.get("llm_usage_reason")

    def _record_usage(
        self,
        model: str,
        messages: list[dict[str, str]],
        usage: Mapping[str, int] | None,
        llm_api: str,
    ) -> None:
        prompt_tokens = token_counter(model=model, messages=messages)
        usage_data: Mapping[str, int] = usage or {}
        all_tokens = TokenCounterCompat(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        logger.info(f"[sdk1][LLM][{model}][{llm_api}] Prompt Tokens: {prompt_tokens}")
        logger.info(f"[sdk1][LLM][{model}][{llm_api}] LLM Usage: {all_tokens}")

        Audit().push_usage_data(
            platform_api_key=self._platform_api_key,
            token_counter=all_tokens,
            event_type="llm",
            model_name=model,
            kwargs={"provider": self.adapter.get_provider(), **self.platform_kwargs},
        )

    # Finish reasons indicating a safety/policy refusal across providers:
    # - "refusal": Anthropic
    # - "content_filter": OpenAI / Azure OpenAI
    REFUSAL_FINISH_REASONS = {"refusal", "content_filter"}

    def _raise_for_empty_response(self, finish_reason: str | None) -> NoReturn:
        """Raise an appropriate error when the LLM response content is None.

        This typically happens when the LLM provider refuses to generate a
        response (e.g. Anthropic's safety filters, OpenAI's content filter)
        or returns an empty response.

        Args:
            finish_reason: The finish_reason from the LLM response.

        Raises:
            LLMError: With a descriptive message based on the finish_reason.
        """
        if finish_reason in self.REFUSAL_FINISH_REASONS:
            raise LLMError(
                message=(
                    "The LLM refused to generate a response due to safety "
                    f"restrictions (finish_reason: {finish_reason!r}). "
                    "Please review your prompt and try again."
                ),
                status_code=400,
            )
        raise LLMError(
            message=(
                f"The LLM returned an empty response "
                f"(finish_reason: {finish_reason}). This may indicate "
                f"the model could not generate content for the given prompt."
            ),
            status_code=500,
        )

    def _process_stream_chunk(
        self,
        chunk: dict[str, object],
        callback_manager: object | None,
        has_yielded_content: bool = False,
    ) -> LLMResponseCompat | None:
        """Process a single streaming chunk and return a response if content.

        Args:
            chunk: A streaming chunk from litellm.
            callback_manager: Optional callback manager for stream events.
            has_yielded_content: Whether any content has already been yielded.

        Returns:
            LLMResponseCompat with the text chunk, or None if no content.

        Raises:
            LLMError: If the chunk indicates a refusal and no content has
                been yielded yet. If content was already streamed, logs a
                warning instead to avoid confusing late errors.
        """
        if not chunk.get("choices"):
            return None

        finish_reason = chunk["choices"][0].get("finish_reason")
        if finish_reason in self.REFUSAL_FINISH_REASONS:
            if has_yielded_content:
                logger.warning(
                    "[sdk1][LLM] Provider sent refusal after content was "
                    "already streamed. Partial content may have been returned."
                )
                return None
            self._raise_for_empty_response(finish_reason)

        text = chunk["choices"][0].get("delta", {}).get("content", "")
        if not text:
            return None

        if callback_manager and hasattr(callback_manager, "on_stream"):
            callback_manager.on_stream(text)

        stream_response = LLMResponseCompat(text)
        stream_response.delta = text
        return stream_response

    def _post_process_response(
        self,
        response_text: str,
        extract_json: bool,
        post_process_fn: Callable[[LLMResponseCompat, bool, str], dict[str, object]]
        | None,
    ) -> tuple[str, dict[str, object]]:
        post_processed_output: dict[str, object] = {}

        # Save original text before any modifications
        original_text = response_text

        if extract_json:
            start = response_text.find(LLM.JSON_CONTENT_MARKER)
            if start != -1:
                response_text = response_text[
                    start + len(LLM.JSON_CONTENT_MARKER) :
                ].lstrip()
            end = response_text.rfind(LLM.JSON_CONTENT_MARKER)
            if end != -1:
                response_text = response_text[:end].rstrip()
            match = LLM.JSON_REGEX.search(response_text)
            if match:
                response_text = match.group(0)

        if post_process_fn:
            try:
                response_compat = LLMResponseCompat(response_text)
                post_processed_output = post_process_fn(
                    response_compat, extract_json, original_text
                )
                # Needed as the text is modified in place.
                response_text = response_compat.text
            except Exception as e:
                logger.error(
                    f"[sdk1][LLM][complete] Failed to post process response: {e}"
                )
                post_processed_output = {}

        return (response_text, post_processed_output)


class LLMCompat:
    """Compatibility wrapper that emulates the llama-index LLM interface.

    This class emulates ``llama_index.core.llms.llm.LLM`` without requiring
    the llama-index dependency. It allows llama-index components like
    SubQuestionQueryEngine, QueryFusionRetriever, and RouterQueryEngine
    to work with SDK1's LLM.

    Unlike :class:`EmbeddingCompat` (which inherits from llama-index's
    ``BaseEmbedding``), this class is a plain Python object with no
    llama-index inheritance. The prompt-service's ``RetrieverLLM``
    provides the llama-index base class and delegates to this wrapper.

    Prefer :meth:`from_llm` when an SDK1 ``LLM`` instance already
    exists — it reuses the instance directly, bypassing ``__init__``.
    """

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, object] | None = None,
        adapter_instance_id: str = "",
        tool: BaseTool | None = None,
        usage_kwargs: dict[str, object] | None = None,
        system_prompt: str = "",
        kwargs: dict[str, object] | None = None,
        capture_metrics: bool = False,
    ) -> None:
        """Initialize the LLMCompat wrapper for compatibility.

        Args:
            adapter_id: Adapter identifier for LLM model
            adapter_metadata: Configuration metadata for the adapter
            adapter_instance_id: Instance identifier for the adapter
            tool: BaseTool instance for tool-specific operations
            usage_kwargs: Usage tracking parameters
            system_prompt: System prompt for the LLM
            kwargs: Additional keyword arguments for configuration
            capture_metrics: Whether to capture performance metrics
        """
        adapter_metadata = adapter_metadata or {}
        usage_kwargs = usage_kwargs or {}
        kwargs = kwargs or {}

        self._llm_instance = LLM(
            adapter_id=adapter_id,
            adapter_metadata=adapter_metadata,
            adapter_instance_id=adapter_instance_id,
            tool=tool,
            usage_kwargs=usage_kwargs,
            system_prompt=system_prompt,
            kwargs=kwargs,
            capture_metrics=capture_metrics,
        )
        self._tool = tool
        self._adapter_instance_id = adapter_instance_id

        # For compatibility with SDK Callback Manager.
        self.model_name = self._llm_instance.get_model_name()
        self.callback_manager = None

        if not PlatformHelper.is_public_adapter(adapter_id=adapter_instance_id):
            if self._tool:
                platform_api_key = self._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
            else:
                platform_api_key = os.environ.get(ToolEnv.PLATFORM_API_KEY, "")

            from unstract.sdk1.utils.callback_manager import CallbackManager

            CallbackManager.set_callback(
                platform_api_key=platform_api_key,
                model=self,
                kwargs={
                    **self._llm_instance.platform_kwargs,
                    "adapter_instance_id": adapter_instance_id,
                },
            )

    # ── Properties (llama-index interface) ───────────────────────────────────

    @property
    def metadata(self) -> LLMMetadata:
        """Return LLM metadata for llama-index compatibility."""
        return LLMMetadata(
            is_chat_model=True,
            model_name=self._llm_instance.get_model_name(),
        )

    # ── Sync methods (llama-index interface) ─────────────────────────────────
    # All LLM calls delegate to self._llm_instance (SDK1 LLM) so that
    # litellm invocation, error handling, and usage auditing stay in one
    # place.

    def chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponse:
        """Synchronous chat completion.

        Extracts the last user message as the prompt and delegates to
        ``LLM.complete()``.
        """
        prompt = self._messages_to_prompt(messages)
        result = self._llm_instance.complete(prompt, **kwargs)
        resp = result["response"]
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=resp.text),
            raw=resp.raw,
        )

    def complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponse:
        """Synchronous completion."""
        result = self._llm_instance.complete(prompt, **kwargs)
        resp = result["response"]
        return CompletionResponse(text=resp.text, raw=resp.raw)

    def stream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> Generator[ChatResponse, None, None]:
        """Streaming chat - not implemented."""
        raise NotImplementedError("stream_chat is not supported by LLMCompat.")

    def stream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> Generator[CompletionResponse, None, None]:
        """Streaming completion - not implemented."""
        raise NotImplementedError("stream_complete is not supported by LLMCompat.")

    # ── Async methods (llama-index interface) ────────────────────────────────

    async def achat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> ChatResponse:
        """Asynchronous chat completion.

        Extracts the last user message as the prompt and delegates to
        ``LLM.acomplete()``.
        """
        prompt = self._messages_to_prompt(messages)
        result = await self._llm_instance.acomplete(prompt, **kwargs)
        resp = result["response"]
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content=resp.text),
            raw=resp.raw,
        )

    async def acomplete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> CompletionResponse:
        """Asynchronous completion."""
        result = await self._llm_instance.acomplete(prompt, **kwargs)
        resp = result["response"]
        return CompletionResponse(text=resp.text, raw=resp.raw)

    async def astream_chat(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Async streaming chat - not implemented."""
        raise NotImplementedError("astream_chat is not supported by LLMCompat.")

    async def astream_complete(
        self,
        prompt: str,
        formatted: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Async streaming completion - not implemented."""
        raise NotImplementedError("astream_complete is not supported by LLMCompat.")

    # ── Helper methods ───────────────────────────────────────────────────────

    @staticmethod
    def _messages_to_prompt(messages: Sequence[ChatMessage]) -> str:
        """Flatten a message sequence into a single prompt string.

        Concatenates all messages with role prefixes so that
        system-level task instructions (e.g. from llama-index's
        ``LLMQuestionGenerator`` or ``KeywordTableIndex``) are
        preserved when forwarded to ``LLM.complete()``.
        """
        parts: list[str] = []
        for msg in messages:
            role = getattr(msg.role, "value", str(msg.role))
            content = msg.content or ""
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    # ── Factory methods ────────────────────────────────────────────────────

    @classmethod
    def from_llm(cls, llm: "LLM") -> "LLMCompat":
        """Create an LLMCompat instance reusing an existing SDK1 LLM.

        Reuses the already-initialised ``LLM`` object directly, avoiding
        redundant adapter validation and ``PlatformHelper`` calls that
        would occur if we re-created the instance from scratch.

        Args:
            llm: An SDK1 LLM instance.

        Returns:
            A new LLMCompat wrapping the same LLM instance.
        """
        instance = cls.__new__(cls)
        instance._llm_instance = llm
        instance._tool = llm._tool
        instance._adapter_instance_id = llm._adapter_instance_id

        # For compatibility with SDK Callback Manager.
        instance.model_name = llm.get_model_name()
        instance.callback_manager = None

        if not PlatformHelper.is_public_adapter(adapter_id=llm._adapter_instance_id):
            if llm._tool:
                platform_api_key = llm._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
            else:
                platform_api_key = os.environ.get(ToolEnv.PLATFORM_API_KEY, "")

            from unstract.sdk1.utils.callback_manager import CallbackManager

            CallbackManager.set_callback(
                platform_api_key=platform_api_key,
                model=instance,
                kwargs={
                    **llm.platform_kwargs,
                    "adapter_instance_id": llm._adapter_instance_id,
                },
            )

        return instance

    # ── SDK1 compatibility methods ───────────────────────────────────────────

    def get_model_name(self) -> str:
        """Gets the name of the LLM model."""
        return self._llm_instance.get_model_name()

    def get_metrics(self) -> dict[str, object]:
        """Get captured metrics."""
        return self._llm_instance.get_metrics()

    def get_usage_reason(self) -> object:
        """Get usage reason from platform kwargs."""
        return self._llm_instance.get_usage_reason()

    def test_connection(self) -> bool:
        """Test connection to the LLM provider."""
        return self._llm_instance.test_connection()
