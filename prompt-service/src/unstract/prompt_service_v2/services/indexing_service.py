from unstract.prompt_service.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service_v2.utils.file_utils import FileUtils
from unstract.sdk.dto import (
    ChunkingConfig,
    FileInfo,
    InstanceIdentifiers,
    ProcessingOptions,
)
from unstract.sdk.embedding import Embedding
from unstract.sdk.index_v2 import Index
from unstract.sdk.vector_db import VectorDB


class IndexingService:

    @staticmethod
    def index(
        execution_source: str,
        chuking_config: ChunkingConfig,
        file_info: FileInfo,
        instance_identifiers: InstanceIdentifiers,
        processing_options: ProcessingOptions,
        platform_key: str,
        run_id: str,
        extracted_text: str,
    ) -> str:

        try:
            fs_instance = FileUtils.get_fs_instance(execution_source=execution_source)
            util = PromptServiceBaseTool(platform_key=platform_key)
            index: Index = Index(tool=util, run_id=run_id, capture_metrics=True)
            doc_id: str = index.generate_index_key(
                chuking_config=chuking_config,
                file_info=file_info,
                instance_identifiers=instance_identifiers,
                fs=fs_instance,
            )

            # TODO Write a Util to get triad instances
            embedding = Embedding(
                tool=util,
                adapter_instance_id=instance_identifiers.embedding_instance_id,
                usage_kwargs=processing_options.usage_kwargs,
            )

            vector_db = VectorDB(
                tool=util,
                adapter_instance_id=instance_identifiers.vector_db_instance_id,
                embedding=embedding,
            )

            doc_id_found = index.is_document_indexed(
                instance_identifiers=instance_identifiers,
                doc_id=doc_id,
                processing_options=processing_options,
                embedding=embedding,
                vector_db=vector_db,
            )
            if doc_id_found:
                return doc_id
            # Index and return doc_id
            index.perform_indexing(
                instance_identifiers=instance_identifiers,
                chunking_config=chuking_config,
                vector_db=vector_db,
                doc_id=doc_id,
                extracted_text=extracted_text,
                doc_id_found=doc_id_found,
            )
            return doc_id
        finally:
            vector_db.close()
