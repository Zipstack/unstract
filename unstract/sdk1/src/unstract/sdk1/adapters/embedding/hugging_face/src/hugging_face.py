import os
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    ADAPTER_NAME = "adapter_name"
    MODEL = "model_name"
    TOKENIZER_NAME = "tokenizer_name"
    MAX_LENGTH = "max_length"
    NORMALIZE = "normalize"


class HuggingFace(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("HuggingFace")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "huggingface|90ec9ec2-1768-4d69-8fb1-c88b95de5e5a"

    @staticmethod
    def get_name() -> str:
        return "HuggingFace"

    @staticmethod
    def get_description() -> str:
        return "HuggingFace Embedding"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/huggingface.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            max_length: int | None = (
                int(self.config.get(Constants.MAX_LENGTH, 0))
                if self.config.get(Constants.MAX_LENGTH)
                else None
            )
            embedding: BaseEmbedding = HuggingFaceEmbedding(
                model_name=str(self.config.get(Constants.MODEL)),
                tokenizer_name=str(self.config.get(Constants.TOKENIZER_NAME)),
                normalize=bool(self.config.get(Constants.NORMALIZE)),
                embed_batch_size=embedding_batch_size,
                max_length=max_length,
            )

            return embedding
        except Exception as e:
            raise AdapterError(str(e))
