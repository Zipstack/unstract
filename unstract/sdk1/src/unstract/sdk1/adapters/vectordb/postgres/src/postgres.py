import os
from typing import Any
from urllib.parse import quote_plus

import psycopg2
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.vector_stores.postgres import PGVectorStore
from psycopg2._psycopg import connection
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter


class Constants:
    DATABASE = "database"
    HOST = "host"
    PASSWORD = "password"
    PORT = "port"
    USER = "user"
    SCHEMA = "schema"
    ENABLE_SSL = "enable_ssl"


class Postgres(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: connection | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._schema_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Postgres", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "postgres|70ab6cc2-e86a-4e5a-896f-498a95022d34"

    @staticmethod
    def get_name() -> str:
        return "Postgres"

    @staticmethod
    def get_description() -> str:
        return "Postgres VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/postgres.png"

    def get_vector_db_instance(self) -> BasePydanticVectorStore:
        return self._vector_db_instance

    def _get_vector_db_instance(self) -> BasePydanticVectorStore:
        try:
            encoded_password = quote_plus(str(self._config.get(Constants.PASSWORD)))
            dimension = self._config.get(
                VectorDbConstants.EMBEDDING_DIMENSION,
                VectorDbConstants.DEFAULT_EMBEDDING_SIZE,
            )
            self._collection_name = VectorDBHelper.get_collection_name(
                self._config.get(VectorDbConstants.VECTOR_DB_NAME),
                dimension,
            )
            self._schema_name = self._config.get(
                Constants.SCHEMA,
                VectorDbConstants.DEFAULT_VECTOR_DB_NAME,
            )
            vector_db: BasePydanticVectorStore = PGVectorStore.from_params(
                database=self._config.get(Constants.DATABASE),
                schema_name=self._schema_name,
                host=self._config.get(Constants.HOST),
                password=encoded_password,
                port=str(self._config.get(Constants.PORT)),
                user=self._config.get(Constants.USER),
                table_name=self._collection_name,
                embed_dim=dimension,
            )
            if self._config.get(Constants.ENABLE_SSL, True):
                ssl_mode = "require"
            else:
                ssl_mode = "disable"
            self._client = psycopg2.connect(
                database=self._config.get(Constants.DATABASE),
                host=self._config.get(Constants.HOST),
                user=self._config.get(Constants.USER),
                password=self._config.get(Constants.PASSWORD),
                port=str(self._config.get(Constants.PORT)),
                sslmode=ssl_mode,
            )

            return vector_db
        except Exception as e:
            raise AdapterError(str(e))

    def test_connection(self) -> bool:
        vector_db = self.get_vector_db_instance()
        test_result: bool = VectorDBHelper.test_vector_db_instance(vector_store=vector_db)

        # Delete the collection that was created for testing
        if self._client is not None:
            self._client.cursor().execute(
                f"DROP TABLE IF EXISTS "
                f"{self._schema_name}.data_{self._collection_name} CASCADE"
            )
            self._client.commit()

        return test_result

    def close(self, **kwargs: Any) -> None:
        if self._client:
            self._client.close()
