import os
import time
from typing import Any

from llama_index.core.embeddings import BaseEmbedding

from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.no_op.src.no_op_custom_embedding import (
    NoOpCustomEmbedding,
)


class NoOpEmbedding(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("NoOpCustomEmbedding")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "noOpEmbedding|ff223003-fee8-4079-b288-e86215e6b39a"

    @staticmethod
    def get_name() -> str:
        return "No Op Embedding"

    @staticmethod
    def get_description() -> str:
        return "No Op Embedding"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/noOpEmbedding.png"

    @staticmethod
    def get_provider() -> str:
        return "NoOp"

    def get_embedding_instance(self) -> BaseEmbedding:
        embedding: BaseEmbedding = NoOpCustomEmbedding(
            embed_dim=1, wait_time=self.config.get("wait_time")
        )
        return embedding

    def test_connection(self) -> bool:
        time.sleep(self.config.get("wait_time"))
        return True
