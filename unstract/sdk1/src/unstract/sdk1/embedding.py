"""LiteLLM-based Embedding helper.
"""
from __future__ import annotations

from typing import Any

import litellm
from pydantic import ValidationError

from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.adapters.llm1.base import (
    AWSBedrockParams,
    AzureOpenAIParams,
    OllamaParams,
    OpenAIParams,
    VertexAIParams,
)


class Embedding:
    """Unified embedding interface backed by LiteLLM."""

    _TEST_SNIPPET = "Hello, I am Unstract"

    def __init__(
        self,
        adapter_id: str,
        adapter_metadata: dict[str, Any],
        kwargs: dict[str, Any] = {},
    ) -> None:
        self._adapter_id = adapter_id
        self._adapter_metadata = adapter_metadata

        self.kwargs = kwargs
        
        self._extract_kwargs()
        self.length = len(self.get_query_embedding(self._TEST_SNIPPET))

    def get_query_embedding(self, query: str) -> list[float]:
        """Return embedding vector for query string."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")
        del kwargs["temperature"]
        resp = litellm.embedding(model=model, input=[query], **kwargs)
        return resp["data"][0]["embedding"]

    def _extract_kwargs(self):
        """
        Extract and validate embedding parameters from adapter metadata.
        """
        # Extract provider from adapter ID.
        # Format: <embedding_provider_name>|<uuid>
        self.provider = self._adapter_id.split("|")[0]
        
        # Process adapter metadata.
        # NOTE: Apply metadata transformations before provider args validation.
        try:
            getattr(self, f"_extract_{self.provider}_kwargs")()
        except AttributeError as e:
            raise SdkError("Embedding adapter not supported: " + self.provider)
        except ValidationError as e:
            raise SdkError("Invalid embedding adapter metadata: " + str(e))

    def _extract_azureopenai_kwargs(self):
        self.provider = "azure"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('deployment_name', '')}"
        self._adapter_metadata["api_base"] = self._adapter_metadata.get("azure_endpoint", "").split("?")[0]

        self.kwargs.update(AzureOpenAIParams(**self._adapter_metadata).model_dump())

    def _extract_openai_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"

        self.kwargs.update(OpenAIParams(**self._adapter_metadata).model_dump())

    def _extract_vertexai_kwargs(self):
        self.provider = "vertex_ai"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"
        self._adapter_metadata["vertex_credentials"] = self._adapter_metadata.get("json_credentials", "")
        self._adapter_metadata["vertex_project"] = self._adapter_metadata.get("project", "")
        ss = self._adapter_metadata.get("safety_settings", {})
        self._adapter_metadata["safety_settings"] = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": ss.get("harassment", "BLOCK_ONLY_HIGH")},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": ss.get("hate_speech", "BLOCK_ONLY_HIGH")},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": ss.get("sexual_content", "BLOCK_ONLY_HIGH")},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": ss.get("dangerous_content", "BLOCK_ONLY_HIGH")},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": ss.get("civic_integrity", "BLOCK_ONLY_HIGH")},
        ]

        self.kwargs.update(VertexAIParams(**self._adapter_metadata).model_dump())

    def _extract_bedrock_kwargs(self):
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"
        self._adapter_metadata["aws_region_name"] = self._adapter_metadata.get("region_name", "")

        self.kwargs.update(AWSBedrockParams(**self._adapter_metadata).model_dump())

    def _extract_ollama_kwargs(self):
        self.provider = "ollama_chat"
        self._adapter_metadata["model"] = f"{self.provider}/{self._adapter_metadata.get('model', '')}"
        self._adapter_metadata["api_base"] = self._adapter_metadata.get("base_url", "")

        self.kwargs.update(OllamaParams(**self._adapter_metadata).model_dump())
