import os
from typing import Any

from llama_index.core.vector_stores.types import VectorStore
from llama_index.vector_stores.milvus import MilvusVectorStore
from pymilvus import MilvusClient
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter


class Constants:
    URI = "uri"
    TOKEN = "token"
    DIM_VALUE = 1536


class Milvus(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: MilvusClient | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Milvus", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "milvus|3f42f6f9-4b8e-4546-95f3-22ecc9aca442"

    @staticmethod
    def get_name() -> str:
        return "Milvus"

    @staticmethod
    def get_description() -> str:
        return "Milvus VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Milvus.png"

    def get_vector_db_instance(self) -> VectorStore:
        return self._vector_db_instance

    def _get_vector_db_instance(self) -> VectorStore:
        try:
            dimension = self._config.get(
                VectorDbConstants.EMBEDDING_DIMENSION,
                VectorDbConstants.DEFAULT_EMBEDDING_SIZE,
            )
            self._collection_name = VectorDBHelper.get_collection_name(
                self._config.get(VectorDbConstants.VECTOR_DB_NAME),
                dimension,
            )
            vector_db: VectorStore = MilvusVectorStore(
                uri=self._config.get(Constants.URI, ""),
                collection_name=self._collection_name,
                token=self._config.get(Constants.TOKEN, ""),
                dim=dimension,
            )
            if vector_db is not None:
                self._client = vector_db.client
            return vector_db
        except Exception as e:
            raise AdapterError(str(e))

    def test_connection(self) -> bool:
        vector_db = self.get_vector_db_instance()
        test_result: bool = VectorDBHelper.test_vector_db_instance(vector_store=vector_db)
        # Delete the collection that was created for testing
        if self._client is not None:
            self._client.drop_collection(self._collection_name)
        return test_result

    def close(self, **kwargs: Any) -> None:
        if self._client:
            self._client.close()
