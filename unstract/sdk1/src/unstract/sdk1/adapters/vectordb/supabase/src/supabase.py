import os
from typing import Any
from urllib.parse import quote_plus

from llama_index.core.vector_stores.types import VectorStore
from llama_index.vector_stores.supabase import SupabaseVectorStore
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter
from vecs import Client


class Constants:
    DATABASE = "database"
    HOST = "host"
    PASSWORD = "password"
    PORT = "port"
    USER = "user"
    COLLECTION_NAME = "base_demo"


class Supabase(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: Client | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Supabase", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "supabase|e6998e3c-3595-48c0-a190-188dbd803858"

    @staticmethod
    def get_name() -> str:
        return "Supabase"

    @staticmethod
    def get_description() -> str:
        return "Supabase VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/supabase.png"

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
                self._config.get(
                    VectorDbConstants.EMBEDDING_DIMENSION,
                    dimension,
                ),
            )
            user = str(self._config.get(Constants.USER))
            password = str(self._config.get(Constants.PASSWORD))
            encoded_password = quote_plus(str(password))
            host = str(self._config.get(Constants.HOST))
            port = str(self._config.get(Constants.PORT))
            db_name = str(self._config.get(Constants.DATABASE))

            postgres_connection_string = (
                f"postgresql://{user}:{encoded_password}@{host}:{port}/{db_name}"
            )
            vector_db: VectorStore = SupabaseVectorStore(
                postgres_connection_string=postgres_connection_string,
                collection_name=self._collection_name,
                dimension=dimension,
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
            self._client.delete_collection(self._collection_name)
        return test_result

    def close(self, **kwargs: Any) -> None:
        if self._client:
            self._client.close()
