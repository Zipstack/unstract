from __future__ import annotations

from typing import Any

import litellm
from llama_index.core.embeddings import BaseEmbedding
from pydantic import ValidationError

from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding1 import adapters
from unstract.sdk1.constants import ToolEnv
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.callback_manager import CallbackManager


class Embedding:
    """Unified embedding interface powered by LiteLLM.
    Internally invokes Unstract embedding adapters.

    Accepts either of the following pairs for init:
    - adapter ID and metadata       (e.g. test connection)
    - adapter instance ID and tool  (e.g. edit adapter)
    """

    _TEST_SNIPPET = "Hello, I am Unstract"

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, Any] = {},
        adapter_instance_id: str = "",
        tool: BaseTool = None,
        kwargs: dict[str, Any] = {},
    ) -> None:
        embedding_config = None

        try:
            if adapter_instance_id:
                if not tool:
                    raise SdkError("Broken LLM adapter tool binding: " + adapter_instance_id)
                embedding_config = PlatformHelper.get_adapter_config(tool, adapter_instance_id)

            if embedding_config:
                self._adapter_id = embedding_config[Common.ADAPTER_ID]
                self._adapter_metadata = embedding_config[Common.ADAPTER_METADATA]
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
            raise SdkError("Embedding adapter not supported: " + self._adapter_id)

        self.kwargs: dict[str, Any] = kwargs
        try:
            self.kwargs.update(self.adapter.validate(self._adapter_metadata))
        except ValidationError as e:
            raise SdkError("Invalid embedding adapter metadata: " + str(e))

        self._length = len(self.get_embedding(self._TEST_SNIPPET))

    def get_embedding(self, text: str) -> list[float]:
        """Return embedding vector for query string."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")
        del kwargs["temperature"]

        resp = litellm.embedding(model=model, input=[text], **kwargs)

        return resp["data"][0]["embedding"]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for list of query strings."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")
        del kwargs["temperature"]

        resp = litellm.embedding(model=model, input=texts, **kwargs)

        return [data.embedding for data in resp["data"]]

    def test_connection(self) -> bool:
        """Test connection to the embedding provider."""
        return self._length > 0


class EmbeddingCompat(BaseEmbedding):
    """Compatibility wrapper for Embedding."""

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, Any] = {},
        adapter_instance_id: str = "",
        tool: BaseTool = None,
        kwargs: dict[str, Any] = {}
    ):
        super().__init__(**kwargs)

        # For compatibility with Prompt Service, SDK indexing and VectorDB.
        self._embedding_instance = Embedding(
            adapter_id=adapter_id,
            adapter_metadata=adapter_metadata,
            adapter_instance_id=adapter_instance_id,
            tool=tool,
            kwargs=kwargs
        )
        self._length = self._embedding_instance._length

        # For compatibility with SDK Callback Manager.
        self.model_name = self._embedding_instance.kwargs.get("model", "")
        self.callback_manager = None

        if not PlatformHelper.is_public_adapter(adapter_id=self._embedding_instance._adapter_instance_id):
            platform_api_key = self._embedding_instance._tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
            CallbackManager.set_callback(
                platform_api_key=platform_api_key,
                model=self._embedding_instance,
                kwargs={
                    **self._embedding_instance.kwargs,
                    "adapter_instance_id": self._embedding_instance._adapter_instance_id,
                },
            )

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embedding_instance.get_embedding(query)
    
    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embedding_instance.get_embedding(text)
    
    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._embedding_instance.get_embeddings(texts)

    def get_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)

    def test_connection(self) -> bool:
        return self._embedding_instance.test_connection()
