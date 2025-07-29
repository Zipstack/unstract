"""LiteLLM powered unified LLM interface.
"""
import logging
import re
from collections.abc import Generator
from typing import Any, Dict, List, Optional, Union

import litellm

# from litellm import get_supported_openai_params
from pydantic import BaseModel, Field, ValidationError

from unstract.sdk1.exceptions import *

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
        logger.info("[sdk1.LLM] Invoking %s with %s", self.provider, messages)
        
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

    def _extract_kwargs(self):
        """
        Extract and validate LLM parameters from adapter metadata.
        """
        # Extract provider from adapter ID.
        # Format: <llm_provider_name>|<uuid>
        self.provider = self._adapter_id.split("|")[0]
        
        # Process adapter metadata.
        # NOTE: Apply metadata transformations before provider args validation.
        try:
            getattr(self, f"_extract_{self.provider}_kwargs")()

            # REF: https://docs.litellm.ai/docs/completion/input#translated-openai-params
            # supported = get_supported_openai_params(model=self.kwargs["model"], custom_llm_provider=self.provider)
            # for s in supported:
            #     if s not in self.kwargs:
            #         logger.warning("Missing supported parameter for '%s': %s", self.provider, s)
        except AttributeError as e:
            raise SdkError("LLM adapter not supported: " + self.provider)
        except ValidationError as e:
            raise SdkError("Invalid LLM adapter metadata: " + str(e))

    def _extract_azureopenai_kwargs(self):
        self.provider = "azure"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('deployment_name', '')}"
        self._adapter_metadata["api_base"] = self._adapter_metadata.get('azure_endpoint', '').split("?")[0]

        self.kwargs = AzureOpenAIParams(**self._adapter_metadata).model_dump()

    def _extract_openai_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs = OpenAIParams(**self._adapter_metadata).model_dump()

    def _extract_vertexai_kwargs(self):
        self.provider = "vertex_ai"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"
        self._adapter_metadata["vertex_credentials"] = self._adapter_metadata.get('json_credentials', '')
        self._adapter_metadata["vertex_project"] = self._adapter_metadata.get('project', '')

        ss_dict = self._adapter_metadata.get('safety_settings', {})
        self._adapter_metadata["safety_settings"] = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": ss_dict.get('harassment', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": ss_dict.get('hate_speech', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": ss_dict.get('sexual_content', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": ss_dict.get('dangerous_content', 'BLOCK_ONLY_HIGH')
            },
            {
                "category": "HARM_CATEGORY_CIVIC_INTEGRITY",
                "threshold": ss_dict.get('civic_integrity', 'BLOCK_ONLY_HIGH')
            },
        ]

        self.kwargs = VertexAIParams(**self._adapter_metadata).model_dump()

    def _extract_bedrock_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"
        self._adapter_metadata["aws_region_name"] = self._adapter_metadata.get('region_name', '')
        self.kwargs = AWSBedrockParams(**self._adapter_metadata).model_dump()

    def _extract_anthropic_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs = AnthropicParams(**self._adapter_metadata).model_dump()

    def _extract_anyscale_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs = AnyscaleParams(**self._adapter_metadata).model_dump()

    def _extract_mistral_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs = MistralParams(**self._adapter_metadata).model_dump()

    def _extract_ollama_kwargs(self):
        self.provider = "ollama_chat"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs = OllamaParams(**self._adapter_metadata).model_dump()