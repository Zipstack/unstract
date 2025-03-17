import logging
from typing import Any, Optional

from flask import Blueprint, request
from unstract.prompt_service_v2.constants import IndexingConstants as IKeys
from unstract.prompt_service_v2.constants import PromptServiceConstants as PSKeys
from unstract.prompt_service_v2.dto import (
    ChunkingConfig,
    FileInfo,
    InstanceIdentifiers,
    ProcessingOptions,
)
from unstract.prompt_service_v2.helper.auth_helper import AuthHelper
from unstract.prompt_service_v2.services.indexing_service import IndexingService
from unstract.prompt_service_v2.utils.request import validate_request_payload

indexing_bp = Blueprint("index", __name__)
logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    "tool_id",
    "extracted_text",
    "embedding_instance_id",
    "vector_db_instance_id",
    "x2text_instance_id",
    "file_path",
    "chunk_size",
    "chunk_overlap",
    "execution_source",
    "run_id",
]


@AuthHelper.auth_required
@indexing_bp.route("/index", methods=["POST"])
def index() -> Any:
    """
    Endpoint for indexing documents into the vector database.

    This API accepts a JSON payload containing document details, processes the
    document, and stores it in the vector database for retrieval.

    Raises:
        BadRequest: If the request payload is missing or invalid.

    Returns:
        str: doc_id
    """
    platform_key = AuthHelper.get_token_from_auth_header(request)
    payload: dict[Any, Any] = request.json
    validate_request_payload(payload, REQUIRED_FIELDS)

    tool_id: str = payload.get(IKeys.TOOL_ID, "")
    embedding_instance_id: str = payload.get(IKeys.EMBEDDING_INSTANCE_ID, "")
    vector_db_instance_id: str = payload.get(IKeys.VECTOR_DB_INSTANCE_ID, "")
    x2text_instance_id: str = payload.get(IKeys.X2TEXT_INSTANCE_ID, "")
    file_path: str = payload.get(IKeys.FILE_PATH, "")
    file_hash: Optional[str] = payload.get(IKeys.FILE_HASH)
    chunk_size: int = payload.get(IKeys.CHUNK_SIZE, 512)  # Default chunk size
    chunk_overlap: int = payload.get(IKeys.CHUNK_OVERLAP, 128)  # Default chunk overlap
    reindex: bool = payload.get(IKeys.REINDEX, False)
    enable_highlight: bool = payload.get(IKeys.ENABLE_HIGHLIGHT, False)
    usage_kwargs: dict[Any, Any] = payload.get(IKeys.USAGE_KWARGS, {})
    extracted_text: str = payload.get(IKeys.EXTRACTED_TEXT, "")
    tags: list[str] = payload.get(IKeys.TAGS, None)
    execution_source = payload.get(IKeys.EXECUTION_SOURCE, None)
    run_id: str = payload.get(PSKeys.RUN_ID, "")

    instance_identifiers = InstanceIdentifiers(
        embedding_instance_id=embedding_instance_id,
        vector_db_instance_id=vector_db_instance_id,
        x2text_instance_id=x2text_instance_id,
        tool_id=tool_id,
        tags=tags,
        llm_instance_id=None,
    )

    file_info = FileInfo(file_path=file_path, file_hash=file_hash)

    chunking_config = ChunkingConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    processing_options = ProcessingOptions(
        reindex=reindex, enable_highlight=enable_highlight, usage_kwargs=usage_kwargs
    )
    doc_id = IndexingService.index(
        chuking_config=chunking_config,
        execution_source=execution_source,
        run_id=run_id,
        file_info=file_info,
        instance_identifiers=instance_identifiers,
        platform_key=platform_key,
        processing_options=processing_options,
        extracted_text=extracted_text,
    )
    response = {
        IKeys.DOC_ID: doc_id,
    }
    return response
