"""Service for indexing reference data using configured profiles.

This service implements the actual indexing workflow by calling external
extraction and indexing services via the PromptTool SDK, following the
same pattern as Prompt Studio's indexing implementation.
"""

import json
import logging
import os
from typing import Any

from django.conf import settings
from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
    PromptIdeBaseTool,
)
from utils.file_storage.constants import FileStorageKeys
from utils.user_context import UserContext

from lookup.models import LookupDataSource, LookupProfileManager
from unstract.sdk1.constants import LogLevel
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.file_storage.constants import StorageType
from unstract.sdk1.file_storage.env_helper import EnvHelper
from unstract.sdk1.prompt import PromptTool
from unstract.sdk1.utils.indexing import IndexingUtils
from unstract.sdk1.utils.tool import ToolUtils

from .document_indexing_service import LookupDocumentIndexingService
from .lookup_index_helper import LookupIndexHelper

logger = logging.getLogger(__name__)


class IndexingService:
    """Service to orchestrate indexing of reference data.

    Uses PromptTool SDK to call external extraction and indexing services,
    similar to Prompt Studio's implementation but adapted for Lookup projects.
    """

    def __init__(self, profile: LookupProfileManager):
        """Initialize indexing service with profile configuration.

        Args:
            profile: LookupProfileManager instance with adapter configuration
        """
        self.profile = profile
        self.chunk_size = profile.chunk_size
        self.chunk_overlap = profile.chunk_overlap
        self.similarity_top_k = profile.similarity_top_k

        # Adapters from profile
        self.llm = profile.llm
        self.embedding_model = profile.embedding_model
        self.vector_store = profile.vector_store
        self.x2text = profile.x2text

    @staticmethod
    def extract_text(
        data_source: LookupDataSource,
        profile: LookupProfileManager,
        org_id: str,
        run_id: str = None,
    ) -> str:
        """Extract text from data source using X2Text adapter via external service.

        Args:
            data_source: LookupDataSource instance to extract
            profile: LookupProfileManager with X2Text adapter configuration
            org_id: Organization ID
            run_id: Optional run ID for tracking

        Returns:
            Extracted text content

        Raises:
            SdkError: If extraction service fails
        """
        # Generate X2Text config hash for tracking
        metadata = profile.x2text.metadata or {}
        x2text_config_hash = ToolUtils.hash_str(json.dumps(metadata, sort_keys=True))

        # Check if already extracted
        is_extracted = LookupIndexHelper.check_extraction_status(
            data_source_id=str(data_source.id),
            profile_manager=profile,
            x2text_config_hash=x2text_config_hash,
            enable_highlight=False,  # Lookup doesn't need highlighting
        )

        # Get file storage instance
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )

        logger.info(f"File storage instance type: {type(fs_instance)}")
        logger.info(
            f"File storage config: {fs_instance.fs if hasattr(fs_instance, 'fs') else 'N/A'}"
        )

        # Construct file paths
        file_path = data_source.file_path
        logger.info(f"Data source file_path from DB: {file_path}")
        logger.info(
            f"Storage type: {StorageType.PERMANENT}, env: {FileStorageKeys.PERMANENT_REMOTE_STORAGE}"
        )

        directory, filename = os.path.split(file_path)
        extract_file_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )

        logger.info(f"Constructed paths - directory: {directory}, filename: {filename}")
        logger.info(f"Extract file path: {extract_file_path}")

        if is_extracted:
            try:
                extracted_text = fs_instance.read(path=extract_file_path, mode="r")
                logger.info(f"Extracted text found for {filename}, reading from file")
                return extracted_text
            except FileNotFoundError as e:
                logger.warning(
                    f"File not found for extraction: {extract_file_path}. {e}. "
                    "Continuing with extraction..."
                )

        # Call extraction service via PromptTool SDK
        usage_kwargs = {"run_id": run_id, "file_name": filename}
        payload = {
            "x2text_instance_id": str(profile.x2text.id),
            "file_path": file_path,
            "enable_highlight": False,
            "usage_kwargs": usage_kwargs.copy(),
            "run_id": run_id,
            "execution_source": "ide",
            "output_file_path": extract_file_path,
        }

        logger.info(
            f"Extraction payload: x2text_id={payload['x2text_instance_id']}, "
            f"file_path={payload['file_path']}, "
            f"execution_source={payload['execution_source']}, "
            f"output_file_path={payload['output_file_path']}"
        )

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        try:
            responder = PromptTool(
                tool=util,
                prompt_host=settings.PROMPT_HOST,
                prompt_port=settings.PROMPT_PORT,
                request_id=None,
            )
            extracted_text = responder.extract(payload=payload)

            # Mark extraction success in IndexManager
            success = LookupIndexHelper.mark_extraction_status(
                data_source_id=str(data_source.id),
                profile_manager=profile,
                x2text_config_hash=x2text_config_hash,
                enable_highlight=False,
            )

            if not success:
                logger.warning(
                    f"Failed to mark extraction success for data source {data_source.id}. "
                    "Extraction completed but status not saved."
                )

            # Update the data source extraction_status field for UI display
            data_source.extraction_status = "completed"
            data_source.save(update_fields=["extraction_status"])

            logger.info(f"Successfully extracted text from {filename}")
            return extracted_text

        except SdkError as e:
            msg = str(e)
            if e.actual_err and hasattr(e.actual_err, "response"):
                msg = e.actual_err.response.json().get("error", str(e))

            # Mark extraction failure in IndexManager
            LookupIndexHelper.mark_extraction_status(
                data_source_id=str(data_source.id),
                profile_manager=profile,
                x2text_config_hash=x2text_config_hash,
                enable_highlight=False,
                extracted=False,
                error_message=msg,
            )

            # Update the data source extraction_status field for UI display
            data_source.extraction_status = "failed"
            data_source.extraction_error = msg
            data_source.save(update_fields=["extraction_status", "extraction_error"])

            raise Exception(f"Failed to extract '{filename}': {msg}") from e

    @staticmethod
    def index_data_source(
        data_source: LookupDataSource,
        profile: LookupProfileManager,
        org_id: str,
        user_id: str,
        extracted_text: str,
        run_id: str = None,
        reindex: bool = True,
    ) -> str:
        """Index extracted text using profile's adapters via external indexing service.

        Args:
            data_source: LookupDataSource instance
            profile: LookupProfileManager with adapter configuration
            org_id: Organization ID
            user_id: User ID
            extracted_text: Pre-extracted text content
            run_id: Optional run ID for tracking
            reindex: Whether to reindex if already indexed

        Returns:
            Document ID from indexing service

        Raises:
            SdkError: If indexing service fails
        """
        # Skip indexing if chunk_size is 0 (full context mode)
        if profile.chunk_size == 0:
            # Generate doc_id for tracking
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
            util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

            doc_id = IndexingUtils.generate_index_key(
                vector_db=str(profile.vector_store.id),
                embedding=str(profile.embedding_model.id),
                x2text=str(profile.x2text.id),
                chunk_size=str(profile.chunk_size),
                chunk_overlap=str(profile.chunk_overlap),
                file_path=data_source.file_path,
                file_hash=None,
                fs=fs_instance,
                tool=util,
            )

            # Update index manager without actual indexing
            LookupIndexHelper.handle_index_manager(
                data_source_id=str(data_source.id),
                profile_manager=profile,
                doc_id=doc_id,
            )

            logger.info("Skipping vector DB indexing since chunk size is 0")
            return doc_id

        # Get adapter IDs
        embedding_model = str(profile.embedding_model.id)
        vector_db = str(profile.vector_store.id)
        x2text_adapter = str(profile.x2text.id)

        # Construct file paths
        directory, filename = os.path.split(data_source.file_path)
        file_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )

        # Generate index key
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        doc_id_key = IndexingUtils.generate_index_key(
            vector_db=vector_db,
            embedding=embedding_model,
            x2text=x2text_adapter,
            chunk_size=str(profile.chunk_size),
            chunk_overlap=str(profile.chunk_overlap),
            file_path=data_source.file_path,
            file_hash=None,
            fs=fs_instance,
            tool=util,
        )

        try:
            usage_kwargs = {"run_id": run_id, "file_name": filename}

            # Check if already indexed (unless reindexing)
            if not reindex:
                indexed_doc_id = LookupDocumentIndexingService.get_indexed_document_id(
                    org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
                )
                if indexed_doc_id:
                    logger.info(f"Document {filename} already indexed: {indexed_doc_id}")
                    return indexed_doc_id

                # Check if currently being indexed
                if LookupDocumentIndexingService.is_document_indexing(
                    org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
                ):
                    raise Exception(f"Document {filename} is currently being indexed")

            # Mark as being indexed
            LookupDocumentIndexingService.set_document_indexing(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )

            logger.info(f"Invoking indexing service for: {doc_id_key}")

            # Build payload for indexing service
            payload = {
                "tool_id": str(data_source.project.id),  # Use project ID as tool ID
                "embedding_instance_id": embedding_model,
                "vector_db_instance_id": vector_db,
                "x2text_instance_id": x2text_adapter,
                "file_path": file_path,
                "file_hash": None,
                "chunk_overlap": profile.chunk_overlap,
                "chunk_size": profile.chunk_size,
                "reindex": reindex,
                "enable_highlight": False,
                "usage_kwargs": usage_kwargs.copy(),
                "extracted_text": extracted_text,
                "run_id": run_id,
                "execution_source": "ide",
            }

            # Call indexing service via PromptTool SDK
            try:
                responder = PromptTool(
                    tool=util,
                    prompt_host=settings.PROMPT_HOST,
                    prompt_port=settings.PROMPT_PORT,
                    request_id=None,
                )
                doc_id = responder.index(payload=payload)

                # Update index manager with doc_id
                LookupIndexHelper.handle_index_manager(
                    data_source_id=str(data_source.id),
                    profile_manager=profile,
                    doc_id=doc_id,
                )

                # Mark as indexed in cache
                LookupDocumentIndexingService.mark_document_indexed(
                    org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
                )

                logger.info(f"Successfully indexed {filename} with doc_id: {doc_id}")
                return doc_id

            except SdkError as e:
                msg = str(e)
                if e.actual_err and hasattr(e.actual_err, "response"):
                    msg = e.actual_err.response.json().get("error", str(e))
                raise Exception(f"Failed to index '{filename}': {msg}") from e

        except Exception as e:
            logger.error(f"Error indexing {filename}: {e}", exc_info=True)
            # Clear indexing status on error
            LookupDocumentIndexingService.clear_indexing_status(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )
            raise

    @classmethod
    def index_with_default_profile(
        cls, project_id: str, org_id: str = None, user_id: str = None
    ) -> dict[str, Any]:
        """Index all completed data sources using the project's default profile.

        Args:
            project_id: UUID of the lookup project
            org_id: Organization ID (if None, gets from UserContext)
            user_id: User ID (if None, gets from UserContext)

        Returns:
            Dict with indexing results summary

        Raises:
            DefaultProfileError: If no default profile exists for project
            ValueError: If project not found
        """
        from lookup.models import LookupProject

        # Get context if not provided
        if org_id is None:
            org_id = UserContext.get_organization_identifier()
        if user_id is None:
            user_id = UserContext.get_user_id()

        try:
            project = LookupProject.objects.get(id=project_id)
        except LookupProject.DoesNotExist:
            raise ValueError(f"Project {project_id} not found")

        # Get default profile
        default_profile = LookupProfileManager.get_default_profile(project)

        # Get all data sources (extraction will be done as part of indexing)
        data_sources = LookupDataSource.objects.filter(project_id=project_id).order_by(
            "-version_number"
        )

        logger.info(f"Found {data_sources.count()} data sources for project {project_id}")

        # Log each data source status
        for ds in data_sources:
            logger.info(f"  - {ds.file_name}: extraction_status={ds.extraction_status}")

        results = {
            "total": data_sources.count(),
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        for data_source in data_sources:
            try:
                logger.info(
                    f"Indexing data source {data_source.id}: {data_source.file_name}"
                )

                # Extract text
                extracted_text = cls.extract_text(
                    data_source=data_source,
                    profile=default_profile,
                    org_id=org_id,
                    run_id=None,
                )

                # Index the extracted text
                doc_id = cls.index_data_source(
                    data_source=data_source,
                    profile=default_profile,
                    org_id=org_id,
                    user_id=user_id,
                    extracted_text=extracted_text,
                    run_id=None,
                    reindex=True,
                )

                results["success"] += 1
                logger.info(
                    f"Successfully indexed {data_source.file_name} with doc_id: {doc_id}"
                )

            except Exception as e:
                results["failed"] += 1
                error_msg = str(e)
                results["errors"].append(
                    {
                        "data_source_id": str(data_source.id),
                        "file_name": data_source.file_name,
                        "error": error_msg,
                    }
                )
                logger.error(f"Failed to index {data_source.file_name}: {error_msg}")

        logger.info(
            f"Indexing complete for project {project_id}: "
            f"{results['success']} successful, {results['failed']} failed"
        )

        return results
