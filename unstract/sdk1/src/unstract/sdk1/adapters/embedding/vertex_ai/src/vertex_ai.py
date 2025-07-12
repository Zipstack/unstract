import json
import os
from typing import Any

from google.auth.transport import requests as google_requests
from google.oauth2.service_account import Credentials
from llama_index.core.embeddings import BaseEmbedding
from llama_index.embeddings.vertex import VertexTextEmbedding
from unstract.sdk.adapters.embedding.embedding_adapter import EmbeddingAdapter
from unstract.sdk.adapters.embedding.helper import EmbeddingHelper
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.exceptions import EmbeddingError


class Constants:
    MODEL = "model"
    PROJECT = "project"
    JSON_CREDENTIALS = "json_credentials"
    EMBED_MODE = "embed_mode"


class VertexAIEmbedding(EmbeddingAdapter):
    def __init__(self, settings: dict[str, Any]):
        super().__init__("Bedrock")
        self.config = settings

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "vertexai|457a256b-e74f-4251-98a0-8864aafb42a5"

    @staticmethod
    def get_name() -> str:
        return "VertextAI"

    @staticmethod
    def get_description() -> str:
        return "VertexAI Embedding"

    @staticmethod
    def get_provider() -> str:
        return "vertexai"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/VertexAI.png"

    def get_embedding_instance(self) -> BaseEmbedding:
        try:
            embedding_batch_size = EmbeddingHelper.get_embedding_batch_size(
                config=self.config
            )
            input_credentials = self.config.get(Constants.JSON_CREDENTIALS, "{}")
            json_credentials = json.loads(input_credentials)

            credentials = Credentials.from_service_account_info(
                info=json_credentials,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )  # type: ignore
            credentials.refresh(google_requests.Request())

            embedding: BaseEmbedding = VertexTextEmbedding(
                model_name=self.config.get(Constants.MODEL),
                project=self.config.get(Constants.PROJECT),
                credentials=credentials,
                embed_mode=self.config.get(Constants.EMBED_MODE),
                embed_batch_size=embedding_batch_size,
            )
            return embedding
        except json.JSONDecodeError:
            raise EmbeddingError(
                "Credentials is not a valid service account JSON, "
                "please provide a valid JSON."
            )
        except Exception as e:
            raise AdapterError(str(e))
