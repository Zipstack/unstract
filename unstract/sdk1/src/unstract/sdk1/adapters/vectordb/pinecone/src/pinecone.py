import logging
import os
from typing import Any

from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.vector_stores.pinecone import PineconeVectorStore
from pinecone import NotFoundException, PodSpec, ServerlessSpec
from pinecone import Pinecone as LLamaIndexPinecone
from unstract.sdk.adapters.exceptions import AdapterError
from unstract.sdk.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk.adapters.vectordb.helper import VectorDBHelper
from unstract.sdk.adapters.vectordb.vectordb_adapter import VectorDBAdapter

logger = logging.getLogger(__name__)


class Constants:
    API_KEY = "api_key"
    ENVIRONMENT = "environment"
    NAMESPACE = "namespace"
    DIMENSION = 1536
    METRIC = "euclidean"
    SPECIFICATION = "spec"
    SPEC_POD = "pod"
    SPEC_SERVERLESS = "serverless"
    CLOUD = "cloud"
    REGION = "region"
    DEFAULT_SPEC_COUNT_VALUE = 1
    DEFAULT_POD_TYPE = "p1.x1"


class Pinecone(VectorDBAdapter):
    def __init__(self, settings: dict[str, Any]):
        self._config = settings
        self._client: LLamaIndexPinecone | None = None
        self._collection_name: str = VectorDbConstants.DEFAULT_VECTOR_DB_NAME
        self._vector_db_instance = self._get_vector_db_instance()
        super().__init__("Pinecone", self._vector_db_instance)

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    @staticmethod
    def get_id() -> str:
        return "pinecone|83881133-485d-4ecc-b1f7-0009f96dc74a"

    @staticmethod
    def get_name() -> str:
        return "Pinecone"

    @staticmethod
    def get_description() -> str:
        return "Pinecone VectorDB"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/pinecone.png"

    def get_vector_db_instance(self) -> BasePydanticVectorStore:
        return self._vector_db_instance

    def _get_vector_db_instance(self) -> BasePydanticVectorStore:
        try:
            self._client = LLamaIndexPinecone(
                api_key=str(self._config.get(Constants.API_KEY))
            )
            dimension = self._config.get(
                VectorDbConstants.EMBEDDING_DIMENSION,
                VectorDbConstants.DEFAULT_EMBEDDING_SIZE,
            )
            collection_name = VectorDBHelper.get_collection_name(
                self._config.get(VectorDbConstants.VECTOR_DB_NAME),
                dimension,
            )
            self._collection_name = collection_name.replace("_", "-").lower()

            specification = self._config.get(Constants.SPECIFICATION)
            if specification == Constants.SPEC_POD:
                environment = self._config.get(Constants.ENVIRONMENT)
                spec = PodSpec(
                    environment=environment,
                    replicas=Constants.DEFAULT_SPEC_COUNT_VALUE,
                    shards=Constants.DEFAULT_SPEC_COUNT_VALUE,
                    pods=Constants.DEFAULT_SPEC_COUNT_VALUE,
                    pod_type=Constants.DEFAULT_POD_TYPE,
                )
            elif specification == Constants.SPEC_SERVERLESS:
                cloud = self._config.get(Constants.CLOUD)
                region = self._config.get(Constants.REGION)
                spec = ServerlessSpec(cloud=cloud, region=region)
            logger.info(f"Setting up Pinecone spec for {spec}")
            try:
                self._client.describe_index(name=self._collection_name)
            except NotFoundException:
                logger.info(f"Index:{self._collection_name} does not exist. Creating it.")
                self._client.create_index(
                    name=self._collection_name,
                    dimension=dimension,
                    metric=Constants.METRIC,
                    spec=spec,
                )
            self.vector_db: BasePydanticVectorStore = PineconeVectorStore(
                index_name=self._collection_name,
                api_key=str(self._config.get(Constants.API_KEY)),
                environment=str(self._config.get(Constants.ENVIRONMENT)),
            )
            return self.vector_db
        except Exception as e:
            raise AdapterError(str(e))

    def test_connection(self) -> bool:
        vector_db = self.get_vector_db_instance()
        test_result: bool = VectorDBHelper.test_vector_db_instance(vector_store=vector_db)
        # Delete the collection that was created for testing
        if self._client:
            self._client.delete_index(self._collection_name)
        return test_result

    def close(self, **kwargs: Any) -> None:
        # Close connection is not defined for this client
        pass

    def delete(self, ref_doc_id: str, **delete_kwargs: dict[Any, Any]) -> None:
        specification = self._config.get(Constants.SPECIFICATION)
        if specification == Constants.SPEC_SERVERLESS:
            # To delete all records representing chunks of a single document,
            # first list the record IDs based on their common ID prefix,
            # and then delete the records by ID:
            try:
                index = self._client.Index(self._collection_name)  # type: ignore
                # Get all record having the ref_doc_id and delete them
                for ids in index.list(prefix=ref_doc_id):
                    logger.info(ids)
                    index.delete(ids=ids)
            except Exception as e:
                raise AdapterError(str(e))
        elif specification == Constants.SPEC_POD:
            if self.vector_db.environment == "gcp-starter":  # type: ignore
                raise AdapterError(
                    "Re-indexing is not supported on Starter indexes. "
                    "Use Serverless or paid plan for Pod spec"
                )
            else:
                super().delete(ref_doc_id=ref_doc_id, **delete_kwargs)

    def add(
        self,
        ref_doc_id: str,
        nodes: list[BaseNode],
    ) -> list[str]:
        for i, node in enumerate(nodes):
            node_id = ref_doc_id + "-" + node.node_id
            nodes[i].id_ = node_id
        return self.vector_db.add(nodes=nodes)
