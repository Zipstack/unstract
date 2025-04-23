import logging

from unstract.prompt_service.core.index_v2 import Index
from unstract.prompt_service.dto import (
    ChunkingConfig,
    FileInfo,
    InstanceIdentifiers,
    ProcessingOptions,
)
from unstract.prompt_service.exceptions import APIError
from unstract.prompt_service.helpers.prompt_ide_base_tool import PromptServiceBaseTool
from unstract.prompt_service.utils.file_utils import FileUtils
from unstract.sdk.embedding import Embedding
from unstract.sdk.utils.indexing_utils import IndexingUtils
from unstract.sdk.vector_db import VectorDB

logger = logging.getLogger(__name__)


class IndexingService:

    @staticmethod
    def index(
        execution_source: str,
        chunking_config: ChunkingConfig,
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
            index: Index = Index(
                tool=util,
                run_id=run_id,
                capture_metrics=True,
                instance_identifiers=instance_identifiers,
                chunking_config=chunking_config,
                processing_options=processing_options,
            )
            doc_id: str = IndexingUtils.generate_index_key(
                vector_db=instance_identifiers.vector_db_instance_id,
                embedding=instance_identifiers.embedding_instance_id,
                file_path=file_info.file_path,
                file_hash=file_info.file_hash,
                x2text=instance_identifiers.x2text_instance_id,
                chunk_size=str(chunking_config.chunk_size),
                chunk_overlap=str(chunking_config.chunk_overlap),
                tool=util,
                fs=fs_instance,
            )
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
                doc_id=doc_id,
                embedding=embedding,
                vector_db=vector_db,
            )

            # Index and return doc_id
            index.perform_indexing(
                vector_db=vector_db,
                doc_id=doc_id,
                extracted_text=extracted_text,
                doc_id_found=doc_id_found,
            )
            return doc_id
        except Exception as e:
            raise APIError(f"Error while indexing : {str(e)}") from e
        finally:
            if "vector_db" in locals():
                vector_db.close()
