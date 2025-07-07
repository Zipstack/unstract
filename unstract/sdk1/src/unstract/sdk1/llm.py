"""LiteLLM-backed implementation of :class:`~unstract.sdk.llm.LLM`.

Only a subset of the v0 behaviours is supported for now: synchronous
``complete`` and streaming ``stream_complete``.  All other calls will raise
:class:`NotImplementedError` so that test-suites can xfail accordingly.

To get supported OpenAI params for any model + provider see:
https://docs.litellm.ai/docs/completion/input#translated-openai-params
"""
from __future__ import annotations

import logging
import re
from collections.abc import Generator
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from unstract.sdk1.utils.exceptions import *
from unstract.sdk1.utils.tokens import num_tokens

try:
    import litellm
except ModuleNotFoundError as exc:  # pragma: no cover – handled by extras
    raise ImportError(
        "`litellm` is required for SDK v1; install the `[v1]` extra\n"
        "    pip install unstract-sdk[v1]"
    ) from exc

__all__ = [
    "LLM", 
    # "ToolLLM",
]

logger = logging.getLogger(__name__)

_MSG_SYSTEM = {"role": "system", "content": "You are a helpful assistant."}

class LLM:
    """Very small wrapper around :pymod:`litellm` chat completions."""

    def __init__(
        self,
        default_system_prompt: str | None = None,
        adapter_id: str | None = None,
        adapter_metadata: Dict[str, Any] | None = None,
    ) -> None:
        self._default_system_prompt = default_system_prompt or _MSG_SYSTEM["content"]
        self._last_usage: Optional[dict[str, Any]] = None
        self._adapter_id = adapter_id
        self._adapter_metadata = adapter_metadata

        self.provider: str = ""
        self.kwargs: dict[str, Any] = {}
        
        self._extract_kwargs()

    def test_connection(self) -> bool:
        """Test connection to the LLM provider."""
        try:
            # if hasattr(self, "model") and self.model not in O1_MODELS:
            #     completion_kwargs["temperature"] = 0.003

            # if hasattr(self, "thinking_dict") and self.thinking_dict is not None:
            #     completion_kwargs["temperature"] = 1

            response = self.complete("The capital of Tamilnadu is ")
            text = response["choices"][0]["message"]["content"]

            find_match = re.search("chennai", text.lower())
            if find_match:
                return True

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
        logger.info("[sdk1.LLM] calling litellm with %s", messages)
        
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

    # ------------------------------------------------------------------
    # Async helpers ------------------------------------------------------
    # ------------------------------------------------------------------
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

    # Convenience alias ----------------------------------------------------

    def get_usage(self) -> Optional[dict[str, Any]]:  # noqa: D401
        """Return usage dict if present (provider specific)."""
        return self._last_usage

    def _extract_kwargs(self):
        """
        Extract and validate LLM parameters from adapter metadata.
        """
        # Extract provider from adapter ID
        # Format: <llm_provider_name>|<uuid>
        self.provider = self._adapter_id.split("|")[0]
        
        # Process adapter metadata
        # NOTE: Apply transformations before model validation.
        try:
            if self.provider == "azureopenai":
                self._adapter_metadata["api_base"] = self._adapter_metadata.get('azure_endpoint', '').split("?")[0]
                self._adapter_metadata["model"] = f"azure/{self._adapter_metadata.get('deployment_name', '')}"

                self.kwargs = AzureOpenAIParams(**self._adapter_metadata).model_dump()
            elif self.provider == "openai":
                self._adapter_metadata["model"] = f"openai/{self._adapter_metadata.get('model', '')}"

                self.kwargs = OpenAIParams(**self._adapter_metadata).model_dump()
            elif self.provider == "vertexai":
                self._adapter_metadata["model"] = f"vertex_ai/{self._adapter_metadata.get('model', '')}"
                self._adapter_metadata["vertex_credentials"] = self._adapter_metadata.get('json_credentials', '')

                self.kwargs = VertexAIParams(**self._adapter_metadata).model_dump()
        except ValidationError as e:
            raise SdkError("Invalid adapter metadata: " + str(e))

        if not self.kwargs:
            raise SdkError("Unsupported provider: " + self.provider)

class LLMParameters(BaseModel):
    """ Base parameters for all LLM providers.
        See https://docs.litellm.ai/docs/completion/input#input-params-1
    """
    model: str
    # The sampling temperature to be used, between 0 and 2.
    temperature: Optional[float] = Field(default=0.1, ge=0, le=2)
    # The number of chat completion choices to generate for each input message.
    n: Optional[int] = 1
    timeout: Optional[Union[float, int]] = 600
    stream: Optional[bool] = False
    max_completion_tokens: Optional[int] = None
    max_tokens: Optional[int] = None
    num_retries: Optional[int] = None

class OpenAIParams(LLMParameters):
    """See https://docs.litellm.ai/docs/providers/openai/"""
    api_key: str
    api_base: str
    api_version: Optional[str] = None

class AzureOpenAIParams(LLMParameters):
    """See https://docs.litellm.ai/docs/providers/azure/#completion---using-azure_ad_token-api_base-api_version"""
    api_base: str
    api_version: Optional[str] = None
    api_key: str
    temperature: Optional[float] = 1

class VertexAIParams(LLMParameters):
    vertex_credentials: str
    safety_settings: Dict[str, str] = None

# FIXME: Backward-compat alias expected by tests
# ToolLLM = LLM
