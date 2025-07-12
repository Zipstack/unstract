import os
import time
from typing import Any

from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import VectorStore
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.no_op.src.no_op_custom_vectordb import (
    NoOpCustomVectorDB,
)
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter


class NoOpVectorDB(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("NoOpVectorDB", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "noOpVectorDb|ca4d6056-4971-4bc8-97e3-9e36290b5bc0"

    @staticmethod
    def get_name() -> str:
        return "No Op VectorDB"

    @staticmethod
    def get_description() -> str:
        return "No Op VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/noOpVectorDb.png"

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
            vector_db: VectorStore = NoOpCustomVectorDB(
                dim=dimension, wait_time=self._config.get(VectorDbConstants.WAIT_TIME)
            )
            self._client = vector_db.client
            return vector_db
        except Exception as e:
            raise AdapterError(str(e))

    def test_connection(self) -> bool:
        time.sleep(self._config.get("wait_time"))
        return True

    def close(self, **kwargs: Any) -> None:
        pass

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        pass

    def add(self, ref_doc_id: str, nodes: list[BaseNode]) -> list[str]:
        mock_result: list[str] = []
        time.sleep(self._config.get("wait_time"))
        return mock_result
