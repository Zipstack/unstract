import logging
import re
from collections.abc import Generator
from typing import Any, Optional

import litellm

# from litellm import get_supported_openai_params
from litellm import get_max_tokens
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.exceptions import LLMError, SdkError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool

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
    MAX_TOKENS_DEFAULT = 4096

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, Any] = {},
        adapter_instance_id: str = "",
        tool: BaseTool = None,
        default_system_prompt: str = "",
        kwargs: dict[str, Any] = {}
    ) -> None:
        llm_config = None

        try:
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

            self.adapter = adapters[self._adapter_id][Common.MODULE]
        except KeyError:
            raise SdkError("LLM adapter not supported: " + self._adapter_id)

        self._default_system_prompt = default_system_prompt or self.SYSTEM_PROMPT
        self._last_usage: Optional[dict[str, Any]] = None

        try:
            self.kwargs = kwargs
            self.kwargs.update(self.adapter.validate(self._adapter_metadata))

            # REF: https://docs.litellm.ai/docs/completion/input#translated-openai-params
            # supported = get_supported_openai_params(model=self.kwargs["model"], custom_llm_provider=self.provider)
            # for s in supported:
            #     if s not in self.kwargs:
            #         logger.warning("Missing supported parameter for '%s': %s", self.adapter.get_provider(), s)
        except ValidationError as e:
            raise SdkError("Invalid LLM adapter metadata: " + str(e))

    def test_connection(self) -> bool:
        """Test connection to the LLM provider."""
        try:
            response = self.complete("What is the capital of Tamilnadu?")
            text = response["choices"][0]["message"]["content"]

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

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Return a standard chat completion dict."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._default_system_prompt},
            {"role": "user", "content": prompt},
        ]
        logger.info("[sdk1.LLM] Invoking %s with %s", self.adapter.get_provider(), messages)
        
        combined_kwargs = {**self.kwargs, **kwargs}
        # if hasattr(self, "model") and self.model not in O1_MODELS:
        #     completion_kwargs["temperature"] = 0.003

        # if hasattr(self, "thinking_dict") and self.thinking_dict is not None:
        #     completion_kwargs["temperature"] = 1

        response: dict[str, Any] = litellm.completion(
            messages=messages,
            **combined_kwargs,
        )

        # Store usage if provider returns it
        self._last_usage = response.get("usage")

        return response

    def stream_complete(
        self,
        prompt: str,
        callback_manager: Any | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        """Yield chunks of text as they arrive from the provider."""
        messages = [
            {"role": "system", "content": self._default_system_prompt},
            {"role": "user", "content": prompt},
        ]
        
        combined_kwargs = {**self.kwargs, **kwargs}
        
        for chunk in litellm.completion(
            messages=messages,
            stream=True,
            stream_options={
                "include_usage": True,
            },
            **combined_kwargs,
        ):
            text = chunk["choices"][0]["delta"].get("content", "")
            if callback_manager and hasattr(callback_manager, "on_stream"):
                callback_manager.on_stream(text)
            yield text

    async def acomplete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Asynchronous chat completion (wrapper around ``litellm.acompletion``)."""
        messages = [
            {"role": "system", "content": self._default_system_prompt},
            {"role": "user", "content": prompt},
        ]
        
        combined_kwargs = {**self.kwargs, **kwargs}

        response = await litellm.acompletion(
            messages=messages,
            **combined_kwargs,
        )
        self._last_usage = response.get("usage")
        return response

    def get_usage(self) -> Optional[dict[str, Any]]:  # noqa: D401
        """Return usage dict if present (provider specific)."""
        return self._last_usage

    @classmethod
    def get_context_window_size(cls, adapter_id: str, adapter_metadata: dict[str, Any]) -> int:
        try:
            model = adapters[adapter_id][Common.MODULE].validate_model(adapter_metadata)
            return get_max_tokens(model)
        except Exception as e:
            logger.warning(f"Failed to get context window size for {adapter_id}: {e}")
            return cls.MAX_TOKENS_DEFAULT

    @classmethod
    def get_max_tokens(cls, adapter_id: str, adapter_metadata: dict[str, Any]) -> int:
        return cls.get_context_window_size(adapter_id, adapter_metadata)

