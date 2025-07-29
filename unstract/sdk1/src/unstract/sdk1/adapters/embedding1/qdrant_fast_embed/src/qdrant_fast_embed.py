import os
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    MODEL = "model_name"
    ADAPTER_NAME = "adapter_name"


class QdrantFastEmbedM(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("QdrantFastEmbedM")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "qdrantfastembed|31e83eee-a416-4c07-9c9c-02392d5bcf7f"

    @staticmethod
    def get_name() -> str:
        return "QdrantFastEmbedM"

    @staticmethod
    def get_description() -> str:
        return "QdrantFastEmbedM LLM"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/qdrant.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding: BaseEmbedding = FastEmbedEmbedding(
                model_name=str(self.config.get(Constants.MODEL))
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
