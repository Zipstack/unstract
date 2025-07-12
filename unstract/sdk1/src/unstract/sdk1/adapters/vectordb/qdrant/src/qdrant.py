import logging
import os
from typing import Any

from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter
from unstract.sdk.exceptions import VectorDBError

logger = logging.getLogger(__name__)


class Constants:
    URL = "url"
    API_KEY = "api_key"


class Qdrant(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: QdrantClient | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Qdrant", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "qdrant|41f64fda-2e4c-4365-89fd-9ce91bee74d0"

    @staticmethod
    def get_name() -> str:
        return "Qdrant"

    @staticmethod
    def get_description() -> str:
        return "Qdrant LLM"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/qdrant.png"

    def get_vector_db_instance(self) -> BasePydanticVectorStore:
        return self._vector_db_instance

    def _get_vector_db_instance(self) -> BasePydanticVectorStore:
        try:
            self._collection_name = VectorDBHelper.get_collection_name(
                self._config.get(VectorDbConstants.VECTOR_DB_NAME),
                self._config.get(VectorDbConstants.EMBEDDING_DIMENSION),
            )
            url = self._config.get(Constants.URL)
            api_key: str | None = self._config.get(Constants.API_KEY, None)
            if api_key:
                self._client = QdrantClient(url=url, api_key=api_key)
            else:
                self._client = QdrantClient(url=url)
            vector_db: BasePydanticVectorStore = QdrantVectorStore(
                collection_name=self._collection_name,
                client=self._client,
                url=url,
                api_key=api_key,
            )
            return vector_db
        except Exception as e:
            raise self.parse_vector_db_err(e) from e

    def test_connection(self) -> bool:
        try:
            vector_db = self.get_vector_db_instance()
            test_result: bool = VectorDBHelper.test_vector_db_instance(
                vector_store=vector_db
            )
            # Delete the collection that was created for testing
            if self._client is not None:
                self._client.delete_collection(self._collection_name)
            return test_result
        except Exception as e:
            raise self.parse_vector_db_err(e) from e

    def close(self, **kwargs: Any) -> None:
        if self._client:
            self._client.close(**kwargs)

    @staticmethod
    def parse_vector_db_err(e: Exception) -> VectorDBError:
        # Avoid wrapping VectorDBError objects again
        if isinstance(e, VectorDBError):
            return e

        if isinstance(e, UnexpectedResponse):
            msg = str(e)
            if e.reason_phrase == "Not Found":
                msg = "Unable to connect to Qdrant, please check vector DB settings."
            elif e.reason_phrase == "Forbidden":
                msg = "Unable to access Qdrant, please check the API key provided."
            return VectorDBError(message=msg, actual_err=e)
        else:
            status_code = None
            if "client has been closed" in str(e):
                status_code = 503
            elif "timeout" in str(e):
                status_code = 504
            return VectorDBError(message=str(e), actual_err=e, status_code=status_code)
