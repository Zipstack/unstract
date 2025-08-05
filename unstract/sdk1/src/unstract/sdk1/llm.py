import logging
import re
from collections.abc import Generator
from typing import Any, Dict, List, Optional

import litellm

# from litellm import get_supported_openai_params
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.llm1 import adapters
from unstract.sdk1.exceptions import LLMError, SdkError

logger = logging.getLogger(__name__)

_MSG_SYSTEM = "You are a helpful assistant."

class LLM:
    """Unified LLM interface powered by LiteLLM.
    Internally invokes Unstract LLM adapters.
    """

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: Dict[str, Any] = {},
        default_system_prompt: str = ""
    ) -> None:
        self._default_system_prompt = default_system_prompt or _MSG_SYSTEM
        self._last_usage: Optional[dict[str, Any]] = None

        self._adapter_id = adapter_id
        self._adapter_metadata = adapter_metadata

        try:
            self.adapter = adapters[adapter_id][Common.MODULE]
        except KeyError:
            raise SdkError("LLM adapter not supported: " + adapter_id)

        try:
            self.kwargs: dict[str, Any] = self.adapter.validate(adapter_metadata)

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
            # if hasattr(self, "model") and self.model not in O1_MODELS:
            #     completion_kwargs["temperature"] = 0.003

            # if hasattr(self, "thinking_dict") and self.thinking_dict is not None:
            #     completion_kwargs["temperature"] = 1

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

    def complete(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Return a standard chat completion dict."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._default_system_prompt},
            {"role": "user", "content": prompt},
        ]
        logger.info("[sdk1.LLM] Invoking %s with %s", self.adapter.get_provider(), messages)
        
        combined_kwargs = {**self.kwargs, **kwargs}

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

    async def acomplete(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
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

    def get_context_window_size(self):
        return self.get_max_tokens(self.kwargs["model"])
