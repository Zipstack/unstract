import logging
import os
import re
from collections.abc import Callable, Generator
from typing import Any, cast

import litellm

# from litellm import get_supported_openai_params
from litellm import get_max_tokens, token_counter
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.audit import Audit
from unstract.sdk1.constants import ToolEnv
from unstract.sdk1.exceptions import LLMError, SdkError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.common import (
    LLMResponseCompat,
    TokenCounterCompat,
    capture_metrics,
)

logger = logging.getLogger(__name__)

# litellm._turn_on_debug()

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

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, Any] = {},
        adapter_instance_id: str = "",
        tool: BaseTool = None,
        system_prompt: str = "",
        kwargs: dict[str, Any] = {}
    ) -> None:
        try:
            llm_config = None

            if adapter_instance_id:
                if not tool:
                    raise SdkError("Broken LLM adapter tool binding: " + adapter_instance_id)
                llm_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)

            if llm_config:
                self._adapter_id = llm_config[Common.ADAPTER_ID]
                self._adapter_metadata = llm_config[Common.ADAPTER_METADATA]
                self._adapter_instance_id = adapter_instance_id
                self._tool = tool
            else:
                self._adapter_id = adapter_id
                if adapter_metadata:
                    self._adapter_metadata = adapter_metadata
                else:
                    self._adapter_metadata = adapters[self._adapter_id][Common.METADATA]
                self._adapter_instance_id = ""
                self._tool = None

            # Retrieve the adapter class.
            self.adapter = adapters[self._adapter_id][Common.MODULE]
        except KeyError:
            raise SdkError("LLM adapter not supported: " + adapter_id or adapter_instance_id)

        try:
            self.platform_kwargs = kwargs
            self.kwargs = self.adapter.validate(self._adapter_metadata)

            # REF: https://docs.litellm.ai/docs/completion/input#translated-openai-params
            # supported = get_supported_openai_params(model=self.kwargs["model"], custom_llm_provider=self.provider)
            # for s in supported:
            #     if s not in self.kwargs:
            #         logger.warning("Missing supported parameter for '%s': %s", self.adapter.get_provider(), s)
        except ValidationError as e:
            raise SdkError("Invalid LLM adapter metadata: " + str(e))

        self._system_prompt = system_prompt or self.SYSTEM_PROMPT

        if self._tool:
            self._platform_api_key = self._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
            if not self._platform_api_key:
                raise SdkError(f"Missing env variable '{ToolEnv.PLATFORM_API_KEY}'")
        else:
            self._platform_api_key = os.environ.get(ToolEnv.PLATFORM_API_KEY, "")

        # Metrics capture.
        self._run_id = self.platform_kwargs.get("run_id")
        self._capture_metrics = self.platform_kwargs.get("capture_metrics")
        self._metrics: dict[str, Any] = {}

    def test_connection(self) -> bool:
        """Test connection to the LLM provider."""
        try:
            response = self.complete("What is the capital of Tamilnadu?")
            text = response["response"]["text"]

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
        except Exception as e:
            logger.error("Failed to test connection for LLM: %s", e)
            raise e

    @capture_metrics
    def complete(self, prompt: str, **kwargs: dict[str, Any]) -> dict[str, Any]:
        """Return a standard chat completion dict and optionally captures metrics
        if run ID is provided.

        Args:
            prompt   (str)   The input text prompt for generating the completion.
            **kwargs (Any)   Additional arguments passed to the completion function.

        Returns:
            dict[str, Any]  : A dictionary containing the result of the completion,
                any processed output, and the captured metrics (if applicable).
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]
        logger.debug(f"[sdk1][LLM]Invoking {self.adapter.get_provider()} completion API")

        completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})

        # if hasattr(self, "model") and self.model not in O1_MODELS:
        #     completion_kwargs["temperature"] = 0.003
        # if hasattr(self, "thinking_dict") and self.thinking_dict is not None:
        #     completion_kwargs["temperature"] = 1

        response: dict[str, Any] = litellm.completion(
            messages=messages,
            **completion_kwargs,
        )
        response_text = response["choices"][0]["message"]["content"]

        self._record_usage(self.kwargs['model'], messages, response.get("usage"), "complete")

        # NOTE:
        # The typecasting was required to stop the type checker from complaining.
        # Improvements in readability are definitely welcome.
        extract_json: bool = cast(bool, kwargs.get("extract_json", False))
        post_process_fn: Callable[[LLMResponseCompat, bool], dict[str, Any]] | None \
            = cast(Callable[[LLMResponseCompat, bool], dict[str, Any]] | None, kwargs.get("process_text", None))

        response_text, post_processed_output = self._post_process_response(
            response_text, extract_json, post_process_fn
        )

        return {"response": { "text": response_text}, **post_processed_output }

    def stream_complete(
        self,
        prompt: str,
        callback_manager: Any | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Yield chunks of text as they arrive from the provider."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]
        logger.debug(f"[sdk1][LLM]Invoking {self.adapter.get_provider()} stream completion API")
        
        completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})
        
        for chunk in litellm.completion(
            messages=messages,
            stream=True,
            stream_options={
                "include_usage": True,
            },
            **completion_kwargs,
        ):
            if chunk.get("usage"):
                self._record_usage(self.kwargs['model'], messages, chunk.get("usage"), "stream_complete")

            text = chunk["choices"][0]["delta"].get("content", "")

            if callback_manager and hasattr(callback_manager, "on_stream"):
                callback_manager.on_stream(text)

            yield text

    async def acomplete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Asynchronous chat completion (wrapper around ``litellm.acompletion``)."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": prompt},
        ]
        logger.debug(f"[sdk1][LLM]Invoking {self.adapter.get_provider()} async completion API")
        
        completion_kwargs = self.adapter.validate({**self.kwargs, **kwargs})

        response = await litellm.acompletion(
            messages=messages,
            **completion_kwargs,
        )
        response_text = response["choices"][0]["message"]["content"]

        self._record_usage(self.kwargs['model'], messages, response.get("usage"), "acomplete")

        return {"response": { "text": response_text}}


    @classmethod
    def get_context_window_size(cls, adapter_id: str, adapter_metadata: dict[str, Any]) -> int:
        """Returns the context window size of the LLM."""
        try:
            model = adapters[adapter_id][Common.MODULE].validate_model(adapter_metadata)
            return get_max_tokens(model)
        except Exception as e:
            logger.warning(f"Failed to get context window size for {adapter_id}: {e}")
            return cls.MAX_TOKENS

    @classmethod
    def get_max_tokens(cls, adapter_instance_id: str, tool: BaseTool, reserved_for_output: int = 0) -> int:
        """Returns the maximum number of tokens limit for the LLM."""
        try:
            llm_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)
            adapter_id = llm_config[Common.ADAPTER_ID]
            adapter_metadata = llm_config[Common.ADAPTER_METADATA]

            model = adapters[adapter_id][Common.MODULE].validate_model(adapter_metadata)

            return get_max_tokens(model) - reserved_for_output
        except Exception as e:
            logger.warning(f"Failed to get context window size for {adapter_instance_id}: {e}")
            return cls.MAX_TOKENS - reserved_for_output

    def get_metrics(self):
        return self._metrics

    def get_usage_reason(self):
        return self.platform_kwargs.get("llm_usage_reason")

    def _record_usage(self, model: str, messages: list[dict[str, str]], usage: Any, llm_api: str):
        prompt_tokens = token_counter(model=model, messages=messages)
        all_tokens = TokenCounterCompat(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        logger.info(f"[sdk1][LLM][{model}][{llm_api}] Prompt Tokens: {prompt_tokens}")
        logger.info(f"[sdk1][LLM][{model}][{llm_api}] LLM Usage: {all_tokens}")

        Audit().push_usage_data(
            platform_api_key=self._platform_api_key,
            token_counter=all_tokens,
            event_type="llm",
            model_name=model,
            kwargs={
                "provider": self.adapter.get_provider(),
                **self.platform_kwargs
            }
        )

    def _post_process_response(
        self, response_text: str, extract_json: bool, post_process_fn: Callable[[LLMResponseCompat, bool], dict[str, Any]] | None
    ) -> tuple[str, dict[str, Any]]:
        post_processed_output: dict[str, Any] = {}

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
                post_processed_output = post_process_fn(response_compat, extract_json)
                # Needed as the text is modified in place.
                response_text = response_compat.text
            except Exception as e:
                logger.error(f"[sdk1][LLM][complete] Failed to post process response: {e}")
                post_processed_output = {}

        return (response_text, post_processed_output)

