import os
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.ollama import OllamaEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    MODEL = "model_name"
    ADAPTER_NAME = "adapter_name"
    BASE_URL = "base_url"


class Ollama(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Ollama")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "ollama|d58d7080-55a9-4542-becd-8433528e127b"

    @staticmethod
    def get_name() -> str:
        return "Ollama"

    @staticmethod
    def get_description() -> str:
        return "Ollama Embedding"

    @staticmethod
    def get_provider() -> str:
        return "ollama"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/ollama.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            embedding: BaseEmbedding = OllamaEmbedding(
                model_name=str(self.config.get(Constants.MODEL)),
                base_url=str(self.config.get(Constants.BASE_URL)),
                embed_batch_size=embedding_batch_size,
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
