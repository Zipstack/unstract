import logging
from collections.abc import Sequence
from typing import Any

from deprecated import deprecated
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.indices.base import IndexType
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, Document
from llama_index.core.vector_stores.types import (
    BasePydanticVectorStore,
    VectorStore,
    VectorStoreQueryResult,
)

from unstract.sdk1.adapters.vectordb import adapters
from unstract.sdk1.adapters.vectordb.constants import VectorDbConstants
from unstract.sdk1.adapters.vectordb.exceptions import parse_vector_db_err
from unstract.sdk1.constants import Common, LogLevel, ToolEnv
from unstract.sdk1.embedding import Embedding
from unstract.sdk1.exceptions import SdkError, VectorDBError
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool

logger = logging.getLogger(__name__)


class VectorDB:
    """Class to handle VectorDB for Unstract Tools."""

    vector_db_adapters = adapters
    DEFAULT_EMBEDDING_DIMENSION = 1536
    EMBEDDING_INSTANCE_ERROR = (
        "Vector DB does not have an embedding initialised."
        "Migrate to VectorDB instead of deprecated ToolVectorDB "
        "and pass in an Embedding to proceed"
    )

    def __init__(
        self,
        tool: BaseTool,
        adapter_instance_id: str | None = None,
        embedding: Embedding | None = None,
    ):
        self._tool = tool
        self._adapter_instance_id = adapter_instance_id
        self._vector_db_instance = None
        self._embedding_instance = None
        self._embedding_dimension = VectorDB.DEFAULT_EMBEDDING_DIMENSION
        self._initialise(embedding)

    def _initialise(self, embedding: Embedding | None = None):
        if embedding:
            self._embedding_instance = embedding._embedding_instance
            self._embedding_dimension = embedding._length
        if self._adapter_instance_id:
            self._vector_db_instance: BasePydanticVectorStore | VectorStore = (
                self._get_vector_db()
            )

    def _get_org_id(self) -> str:
        platform_helper = PlatformHelper(
            tool=self._tool,
            platform_host=self._tool.get_env_or_die(ToolEnv.PLATFORM_HOST),
            platform_port=self._tool.get_env_or_die(ToolEnv.PLATFORM_PORT),
        )
        # fetch org id from bearer token
        platform_details = platform_helper.get_platform_details()
        if not platform_details:
            # Errors are logged by the SDK itself
            raise SdkError("Error getting platform details")
        account_id = platform_details.get("organization_id")
        return account_id

    def _get_vector_db(self) -> BasePydanticVectorStore | VectorStore:
        """Gets an instance of LlamaIndex's VectorStore.

        Returns:
            Union[BasePydanticVectorStore, VectorStore]: Vector store instance
        """
        try:
            if not self._adapter_instance_id:
                raise VectorDBError("Adapter instance ID not set. Initialisation failed")

            vector_db_config = PlatformHelper.get_adapter_config(
                self._tool, self._adapter_instance_id
            )

            vector_db_adapter_id = vector_db_config.get(Common.ADAPTER_ID)
            if vector_db_adapter_id not in self.vector_db_adapters:
                raise SdkError(
                    f"VectorDB adapter not supported : " f"{vector_db_adapter_id}"
                )

            vector_db_adapter = self.vector_db_adapters[vector_db_adapter_id][
                Common.METADATA
            ][Common.ADAPTER]
            vector_db_metadata = vector_db_config.get(Common.ADAPTER_METADATA)
            # Adding the collection prefix and embedding type
            # to the metadata

            if not PlatformHelper.is_public_adapter(adapter_id=self._adapter_instance_id):
                org = self._get_org_id()
                vector_db_metadata[VectorDbConstants.VECTOR_DB_NAME] = org

            vector_db_metadata[VectorDbConstants.EMBEDDING_DIMENSION] = (
                self._embedding_dimension
            )

            self.vector_db_adapter_class = vector_db_adapter(vector_db_metadata)
            return self.vector_db_adapter_class.get_vector_db_instance()
        except Exception as e:
            self._tool.stream_log(
                log=f"Unable to get vector_db {self._adapter_instance_id}: {e}",
                level=LogLevel.ERROR,
            )
            raise VectorDBError(f"Error getting vectorDB instance: {e}") from e

    def index_document(
        self,
        documents: Sequence[Document],
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        show_progress: bool = False,
        **index_kwargs,
    ) -> IndexType:
        if not self._embedding_instance:
            raise VectorDBError(self.EMBEDDING_INSTANCE_ERROR)
        storage_context = self.get_storage_context()
        parser = SentenceSplitter.from_defaults(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            callback_manager=self._embedding_instance.callback_manager,
        )
        return VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=show_progress,
            embed_model=self._embedding_instance,
            transformations=[parser],
            callback_manager=self._embedding_instance.callback_manager,
            **index_kwargs,
        )

    @deprecated(version="0.47.0", reason="Use index_document() instead")
    def get_vector_store_index_from_storage_context(
        self,
        documents: Sequence[Document],
        storage_context: StorageContext | None = None,
        show_progress: bool = False,
        callback_manager=None,
        **kwargs,
    ) -> IndexType:
        if not self._embedding_instance:
            raise VectorDBError(self.EMBEDDING_INSTANCE_ERROR)
        parser = kwargs.get("node_parser")
        return VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=show_progress,
            embed_model=self._embedding_instance,
            node_parser=parser,
            callback_manager=self._embedding_instance.callback_manager,
        )

    def get_vector_store_index(self, **kwargs: Any) -> VectorStoreIndex:
        if not self._embedding_instance:
            raise VectorDBError(self.EMBEDDING_INSTANCE_ERROR)
        return VectorStoreIndex.from_vector_store(
            vector_store=self._vector_db_instance,
            embed_model=self._embedding_instance,
            callback_manager=self._embedding_instance.callback_manager,
        )

    def get_storage_context(self) -> StorageContext:
        return StorageContext.from_defaults(vector_store=self._vector_db_instance)

    def query(self, query) -> VectorStoreQueryResult:
        try:
            return self._vector_db_instance.query(query=query)
        except Exception as e:
            raise parse_vector_db_err(e, self.vector_db_adapter_class) from e

    def delete(self, ref_doc_id: str, **delete_kwargs: Any) -> None:
        if not self.vector_db_adapter_class:
            raise VectorDBError("Vector DB is not initialised properly")
        self.vector_db_adapter_class.delete(
            ref_doc_id=ref_doc_id, delete_kwargs=delete_kwargs
        )

    def add(
        self,
        ref_doc_id,
        nodes: list[BaseNode],
    ) -> list[str]:
        if not self.vector_db_adapter_class:
            raise VectorDBError("Vector DB is not initialised properly")
        self.vector_db_adapter_class.add(
            ref_doc_id=ref_doc_id,
            nodes=nodes,
        )

    def close(self, **kwargs):
        if not self.vector_db_adapter_class:
            raise VectorDBError("Vector DB is not initialised properly")
        self.vector_db_adapter_class.close()

    def get_class_name(self) -> str:
        """Gets the class name of the Llama Index Vector DB.

        Args:
            NA

        Returns:
                Class name
        """
        return self._vector_db_instance.class_name()

    @deprecated("Use VectorDB instead of ToolVectorDB")
    def get_vector_db(
        self, adapter_instance_id: str, embedding_dimension: int
    ) -> BasePydanticVectorStore | VectorStore:
        if not self._vector_db_instance:
            self._adapter_instance_id = adapter_instance_id
            self._initialise()
        return self._vector_db_instance
