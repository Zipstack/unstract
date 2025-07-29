import os
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.google import GooglePaLMEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    MODEL = "model_name"
    API_KEY = "api_key"
    ADAPTER_NAME = "adapter_name"


class PaLM(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Palm")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "palm|a3fc9fda-f02f-405f-bb26-8bd2ace4317e"

    @staticmethod
    def get_name() -> str:
        return "Palm"

    @staticmethod
    def get_description() -> str:
        return "PaLM Embedding"

    @staticmethod
    def get_provider() -> str:
        return "palm"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/PaLM.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            embedding: BaseEmbedding = GooglePaLMEmbedding(
                model_name=str(self.config.get(Constants.MODEL)),
                api_key=str(self.config.get(Constants.API_KEY)),
                embed_batch_size=embedding_batch_size,
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
