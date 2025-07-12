import logging
import os
from typing import Any

import weaviate
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.vector_stores.weaviate import WeaviateVectorStore
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter
from weaviate.classes.init import Auth
from weaviate.exceptions import UnexpectedStatusCodeException

logger = logging.getLogger(__name__)


class Constants:
    URL = "url"
    API_KEY = "api_key"


class Weaviate(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: weaviate.Client | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Weaviate", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "weaviate|294e08df-4e4a-40f2-8f0d-9e4940180ccc"

    @staticmethod
    def get_name() -> str:
        return "Weaviate"

    @staticmethod
    def get_description() -> str:
        return "Weaviate VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/Weaviate.png"

    def get_vector_db_instance(self) -> BasePydanticVectorStore:
        return self._vector_db_instance

    def _get_vector_db_instance(self) -> BasePydanticVectorStore:
        try:
            collection_name = VectorDBHelper.get_collection_name(
                self._config.get(VectorDbConstants.VECTOR_DB_NAME),
                self._config.get(VectorDbConstants.EMBEDDING_DIMENSION),
            )
            # Capitalise the frst letter as Weaviate expects this
            # LLama-index throws the error if not capitalised while using
            # Weaviate
            self._collection_name = collection_name.capitalize()
            self._client = weaviate.connect_to_weaviate_cloud(
                cluster_url=str(self._config.get(Constants.URL)),
                auth_credentials=Auth.api_key(str(self._config.get(Constants.API_KEY))),
            )

            try:
                # Class definition object. Weaviate's autoschema
                # feature will infer properties when importing.
                class_obj = {
                    "class": self._collection_name,
                    "vectorizer": "none",
                }
                # Create the colletion
                self._client.collections.create_from_dict(class_obj)
            except Exception as e:
                if isinstance(e, UnexpectedStatusCodeException):
                    if "already exists" in e.message:
                        logger.warning(f"Collection already exists: {e}")
                else:
                    raise e
            vector_db: BasePydanticVectorStore = WeaviateVectorStore(
                weaviate_client=self._client,
                index_name=self._collection_name,
            )
            return vector_db
        except Exception as e:
            raise AdapterError(str(e))

    def test_connection(self) -> bool:
        vector_db = self.get_vector_db_instance()
        test_result: bool = VectorDBHelper.test_vector_db_instance(vector_store=vector_db)
        # Delete the collection that was created for testing
        if self._client is not None:
            self._client.collections.delete(self._collection_name)
        return test_result

    def close(self, **kwargs: Any) -> None:
        if self._client:
            self._client.close(**kwargs)
