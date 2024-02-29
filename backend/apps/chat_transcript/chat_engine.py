from apps.app_deployment.models import AppDeployment
from llama_index import VectorStoreIndex
from llama_index.chat_engine.types import ChatMode
from llama_index.vector_stores.types import ExactMatchFilter, MetadataFilters
from unstract.sdk.embedding import ToolEmbedding
from unstract.sdk.llm import ToolLLM
from unstract.sdk.tool.stream import StreamMixin
from unstract.sdk.utils.service_context import UNServiceContext
from unstract.sdk.vector_db import ToolVectorDB


class ChatEngine:
    def __init__(self, app_deployment: AppDeployment) -> None:
        self._app_deployment = app_deployment
        # TODO: This should be replaced with logic to get adapter instance ids
        (
            vector_adapater_id,
            embedding_adapter_id,
            llm_adapter_id,
        ) = (
            "48fa2235-968d-43f8-8585-b7eca4fb20d8",
            "cacceb6d-4c1f-436b-bcc0-7ebf3ba045f4",
            "1b68a960-05d6-4cc3-8a44-4d19accba186",
        )
        self._mock_tool = StreamMixin()
        self._vector_db_tool = ToolVectorDB(tool=self._mock_tool)
        self._vector_store = self._vector_db_tool.get_vector_db(
            adapter_instance_id=vector_adapater_id,
            collection_name_prefix="llama_index",
        )

        self._embedding_tool = ToolEmbedding(tool=self._mock_tool)
        self._embedding_model = self._embedding_tool.get_embedding(
            adapter_instance_id=embedding_adapter_id
        )

        self._llm_tool = ToolLLM(tool=self._mock_tool)
        self._llm = self._llm_tool.get_llm(adapter_instance_id=llm_adapter_id)

        # self._llama_debug = LlamaDebugHandler(print_trace_on_end=True)
        self._service_context = UNServiceContext.get_service_context(
            llm=self._llm,
            embed_model=self._embedding_model,
            # additional_callbacks=[
            #     self._llama_debug,
            # ],
        )

        self._index = VectorStoreIndex.from_vector_store(
            self._vector_store,
            service_context=self._service_context,
        )
        # TODO: Below should be replaced based on indexer implementation
        self._filters = [
            ExactMatchFilter(
                key="library",
                value="strength",
            )
        ]

        self._chat_engine = self._index.as_chat_engine(
            chat_mode=ChatMode.CONDENSE_QUESTION,
            filters=MetadataFilters(filters=self._filters),
        )

    def chat(self, message: str) -> str:
        # NOTE: If needed we could use stream chat
        return str(self._chat_engine.chat(message=message))
