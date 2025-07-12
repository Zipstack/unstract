from abc import ABC, abstractmethod
from typing import Any

from llama_index.core import MockEmbedding
from llama_index.core.embeddings import BaseEmbedding
from unstract.sdk.adapters.base import Adapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.enums import AdapterTypes


class EmbeddingAdapter(Adapter, ABC):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name

    @staticmethod
    def get_id() -> str:
        return ""

    @staticmethod
    def get_name() -> str:
        return ""

    @staticmethod
    def get_description() -> str:
        return ""

    @staticmethod
    @abstractmethod
    def get_provider() -> str:
        pass

    @staticmethod
    def get_icon() -> str:
        return ""

    @staticmethod
    def get_adapter_type() -> AdapterTypes:
        return AdapterTypes.EMBEDDING

    def get_embedding_instance(self, embed_config: dict[str, Any]) -> BaseEmbedding:
        """Instantiate the llama index BaseEmbedding class.

        Returns:
            BaseEmbedding: llama index implementation of the Embedding
            Raises exceptions for any error
        """
        return MockEmbedding(embed_dim=1)

    def test_connection(self) -> bool:
        embedding = self.get_embedding_instance()
        test_result: bool = EmbeddingHelper.test_embedding_instance(embedding)
        return test_result
