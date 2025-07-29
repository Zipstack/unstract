import os
from typing import Any

import httpx
from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    ADAPTER_NAME = "adapter_name"
    MODEL = "model"
    API_KEY = "api_key"
    API_VERSION = "api_version"
    AZURE_ENDPOINT = "azure_endpoint"
    DEPLOYMENT_NAME = "deployment_name"
    API_TYPE = "azure"
    TIMEOUT = "timeout"
    DEFAULT_TIMEOUT = 240


class AzureOpenAI(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("AzureOpenAIEmbedding")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "azureopenai|9770f3f6-f8ba-4fa0-bb3a-bef48a00e66f"

    @staticmethod
    def get_name() -> str:
        return "AzureOpenAIEmbedding"

    @staticmethod
    def get_description() -> str:
        return "AzureOpenAI Embedding"

    @staticmethod
    def get_provider() -> str:
        return "azure"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/AzureopenAI.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            timeout = int(self.config.get(Constants.TIMEOUT, Constants.DEFAULT_TIMEOUT))
            httpx_timeout = httpx.Timeout(timeout, connect=60.0)
            httpx_client = httpx.Client(timeout=httpx_timeout)
            embedding: BaseEmbedding = AzureOpenAIEmbedding(
                model=str(self.config.get(Constants.MODEL)),
                deployment_name=str(self.config.get(Constants.DEPLOYMENT_NAME)),
                api_key=str(self.config.get(Constants.API_KEY)),
                api_version=str(self.config.get(Constants.API_VERSION)),
                azure_endpoint=str(self.config.get(Constants.AZURE_ENDPOINT)),
                embed_batch_size=embedding_batch_size,
                api_type=Constants.API_TYPE,
                timeout=timeout,
                http_client=httpx_client,
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
