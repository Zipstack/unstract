import os
from typing import Any

from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.bedrock import BedrockEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    MODEL = "model"
    TIMEOUT = "timeout"
    MAX_RETRIES = "max_retries"
    SECRET_ACCESS_KEY = "aws_secret_access_key"
    ACCESS_KEY_ID = "aws_access_key_id"
    REGION_NAME = "region_name"
    DEFAULT_TIMEOUT = 240
    DEFAULT_MAX_RETRIES = 3


class Bedrock(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Bedrock")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "bedrock|88199741-8d7e-4e8c-9d92-d76b0dc20c91"

    @staticmethod
    def get_name() -> str:
        return "Bedrock"

    @staticmethod
    def get_description() -> str:
        return "Bedrock Embedding"

    @staticmethod
    def get_provider() -> str:
        return "bedrock"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Bedrock.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            embedding: BaseEmbedding = BedrockEmbedding(
                model_name=self.config.get(Constants.MODEL),
                aws_access_key_id=self.config.get(Constants.ACCESS_KEY_ID),
                aws_secret_access_key=self.config.get(Constants.SECRET_ACCESS_KEY),
                region_name=self.config.get(Constants.REGION_NAME),
                timeout=float(
                    self.config.get(Constants.TIMEOUT, Constants.DEFAULT_TIMEOUT)
                ),
                max_retries=int(
                    self.config.get(Constants.MAX_RETRIES, Constants.DEFAULT_MAX_RETRIES)
                ),
                embed_batch_size=embedding_batch_size,
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
