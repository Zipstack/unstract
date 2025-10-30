from __future__ import annotations

import os
from typing import TYPE_CHECKING

import litellm
from llama_index.core.embeddings import BaseEmbedding
from pydantic import ValidationError
from unstract.sdk1.adapters.constants import Common
from unstract.sdk1.adapters.embedding1 import adapters
from unstract.sdk1.constants import ToolEnv
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.utils.callback_manager import CallbackManager

if TYPE_CHECKING:
    from unstract.sdk1.tool.base import BaseTool


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
        adapter_metadata: dict[str, object] = None,
        adapter_instance_id: str = "",
        tool: BaseTool | None = None,
        kwargs: dict[str, object] = None,
    ) -> None:
        """Initialize the Embedding interface.

        Args:
            adapter_id: Adapter identifier for embedding model
            adapter_metadata: Configuration metadata for the adapter
            adapter_instance_id: Instance identifier for the adapter
            tool: BaseTool instance for tool-specific operations
            kwargs: Additional keyword arguments for configuration
        """
        if adapter_metadata is None:
            adapter_metadata = {}
        if kwargs is None:
            kwargs = {}
        try:
            embedding_config = None

            if adapter_instance_id:
                if not tool:
                    raise SdkError(
                        "Broken LLM adapter tool binding: " + adapter_instance_id
                    )
                embedding_config = PlatformHelper.get_adapter_config(
                    tool, adapter_instance_id
                )

            if embedding_config:
                self._adapter_id = embedding_config[Common.ADAPTER_ID]
                self._adapter_metadata = embedding_config[Common.ADAPTER_METADATA]
                self._adapter_instance_id = adapter_instance_id
                self._tool = tool
            else:
                self._adapter_id = adapter_id
                if adapter_metadata:
                    self._adapter_metadata = adapter_metadata
                    self._tool = tool
                else:
                    self._adapter_metadata = adapters[self._adapter_id][Common.METADATA]
                self._adapter_instance_id = ""
                self._tool = None

            # Retrieve the adapter class.
            self.adapter = adapters[self._adapter_id][Common.MODULE]
        except KeyError as e:
            raise SdkError(
                "Embedding adapter not supported: " + adapter_id or adapter_instance_id
            ) from e

        try:
            self.platform_kwargs: dict[str, object] = kwargs
            self.kwargs: dict[str, object] = self.adapter.validate(self._adapter_metadata)
        except ValidationError as e:
            raise SdkError("Invalid embedding adapter metadata: " + str(e)) from e

        self._length = len(self.get_embedding(self._TEST_SNIPPET))

    def get_embedding(self, text: str) -> list[float]:
        """Return embedding vector for query string."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")

        litellm.drop_params = True

        resp = litellm.embedding(model=model, input=[text], **kwargs)

        return resp["data"][0]["embedding"]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for list of query strings."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")

        resp = litellm.embedding(model=model, input=texts, **kwargs)

        return [data.embedding for data in resp["data"]]

    async def get_aembedding(self, text: str) -> list[float]:
        """Return async embedding vector for query string."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")

        resp = await litellm.aembedding(model=model, input=[text], **kwargs)

        return resp["data"][0]["embedding"]

    async def get_aembeddings(self, texts: list[str]) -> list[list[float]]:
        """Return async embedding vectors for list of query strings."""
        kwargs = self.kwargs.copy()
        model = kwargs.pop("model")

        resp = await litellm.aembedding(model=model, input=texts, **kwargs)

        return [data.embedding for data in resp["data"]]

    def test_connection(self) -> bool:
        """Test connection to the embedding provider."""
        return self._length > 0


class EmbeddingCompat(BaseEmbedding):
    """Compatibility wrapper for Embedding."""

    def __init__(
        self,
        adapter_id: str = "",
        adapter_metadata: dict[str, object] = None,
        adapter_instance_id: str = "",
        tool: BaseTool | None = None,
        kwargs: dict[str, object] = None,
    ) -> None:
        """Initialize the EmbeddingCompat wrapper for compatibility.

        Args:
            adapter_id: Adapter identifier for embedding model
            adapter_metadata: Configuration metadata for the adapter
            adapter_instance_id: Instance identifier for the adapter
            tool: BaseTool instance for tool-specific operations
            kwargs: Additional keyword arguments for configuration
        """
        adapter_metadata = adapter_metadata or {}
        kwargs = kwargs or {}
        super().__init__(**kwargs)

        # For compatibility with Prompt Service, SDK indexing and VectorDB.
        self._embedding_instance = Embedding(
            adapter_id=adapter_id,
            adapter_metadata=adapter_metadata,
            adapter_instance_id=adapter_instance_id,
            tool=tool,
            kwargs=kwargs,
        )
        self._length = self._embedding_instance._length
        self._tool = tool

        # For compatibility with SDK Callback Manager.
        self.model_name = self._embedding_instance.kwargs.get("model", "")
        self.callback_manager = None

        if not PlatformHelper.is_public_adapter(
            adapter_id=self._embedding_instance._adapter_instance_id
        ):
            if self._tool:
                platform_api_key = self._embedding_instance._tool.get_env_or_die(
                    ToolEnv.PLATFORM_API_KEY
                )
            else:
                platform_api_key = os.environ.get(ToolEnv.PLATFORM_API_KEY, "")

            CallbackManager.set_callback(
                platform_api_key=platform_api_key,
                model=self,
                kwargs={
                    **self._embedding_instance.platform_kwargs,
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

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._embedding_instance.get_aembedding(query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return await self._embedding_instance.get_aembedding(text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._embedding_instance.get_aembeddings(texts)

    async def get_aquery_embedding(self, query: str) -> list[float]:
        return await self._aget_query_embedding(query)

    def test_connection(self) -> bool:
        return self._embedding_instance.test_connection()
