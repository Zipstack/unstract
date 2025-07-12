import os
from typing import Any

import httpx
from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.openai import OpenAIEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.exceptions import AdapterError


class Constants:
    API_KEY = "api_key"
    MODEL = "model"
    API_BASE_VALUE = "https://api.openai.com/v1/"
    API_BASE_KEY = "api_base"
    ADAPTER_NAME = "adapter_name"
    API_TYPE = "openai"
    TIMEOUT = "timeout"
    DEFAULT_TIMEOUT = 240
    DEFAULT_MODEL = "text-embedding-ada-002"


class OpenAI(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("OpenAI")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "openai|717a0b0e-3bbc-41dc-9f0c-5689437a1151"

    @staticmethod
    def get_name() -> str:
        return "OpenAI"

    @staticmethod
    def get_description() -> str:
        return "OpenAI LLM"

    @staticmethod
    def get_provider() -> str:
        return "openai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/OpenAI.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            timeout = int(self.config.get(Constants.TIMEOUT, Constants.DEFAULT_TIMEOUT))
            httpx_timeout = httpx.Timeout(10.0, connect=60.0)
            httpx_client = httpx.Client(timeout=httpx_timeout)
            embedding: BaseEmbedding = OpenAIEmbedding(
                api_key=str(self.config.get(Constants.API_KEY)),
                api_base=str(
                    self.config.get(Constants.API_BASE_KEY, Constants.API_BASE_VALUE)
                ),
                model=str(self.config.get(Constants.MODEL, Constants.DEFAULT_MODEL)),
                api_type=Constants.API_TYPE,
                timeout=timeout,
                http_client=httpx_client,
            )
            return embedding
        except Exception as e:
            raise AdapterError(str(e))
