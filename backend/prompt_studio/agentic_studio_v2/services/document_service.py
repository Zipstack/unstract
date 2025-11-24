"""Service layer for AgenticDocument operations."""

import logging
from typing import Optional
from uuid import UUID

from django.core.files.uploadedfile import UploadedFile

from prompt_studio.agentic_studio_v2.models import AgenticDocument, AgenticProject

logger = logging.getLogger(__name__)


class AgenticDocumentService:
    """Business logic for managing Agentic Documents."""

    @staticmethod
    def upload_document(
        project_id: UUID,
        file: UploadedFile,
        organization=None,
        user=None,
    ) -> Optional[AgenticDocument]:
        """Upload and create a new document.

        This method:
        1. Validates the project exists
        2. Stores the file using Unstract's file storage
        3. Creates the AgenticDocument record
        4. Triggers async LLMWhisperer processing (if configured)

        Args:
            project_id: UUID of the parent project
            file: Uploaded file object
            organization: Organization instance
            user: User uploading the document

        Returns:
            AgenticDocument instance or None
        """
        try:
            project = AgenticProject.objects.get(id=project_id)
        except AgenticProject.DoesNotExist:
            logger.error(f"Project {project_id} not found")
            return None

        # TODO: Store file using AgenticStudioFileHelper
        # from utils.file_storage.helpers.agentic_studio_helper import (
        #     AgenticStudioFileHelper,
        # )
        # stored_path = AgenticStudioFileHelper.store_document(
        #     organization_id=str(organization.id),
        #     project_id=str(project_id),
        #     file=file,
        # )

        # For now, use a placeholder path
        stored_path = f"agentic_studio/{project_id}/{file.name}"

        # Create document record
        document = AgenticDocument.objects.create(
            project=project,
            original_filename=file.name,
            stored_path=stored_path,
            size_bytes=file.size,
            organization=organization,
        )

        logger.info(
            f"Created AgenticDocument: {document.id} - {document.original_filename}"
        )

        # TODO: Trigger async processing task
        # from prompt_studio.agentic_studio_v2.tasks import process_document_task
        # job = process_document_task.delay(str(document.id), "raw_text")
        # document.processing_job_id = job.id
        # document.save(update_fields=["processing_job_id"])

        return document

    @staticmethod
    def get_processing_status(doc_id: UUID) -> dict:
        """Get detailed processing status for a document.

        Args:
            doc_id: UUID of the document

        Returns:
            Dict with status information
        """
        try:
            document = AgenticDocument.objects.get(id=doc_id)
        except AgenticDocument.DoesNotExist:
            return {"status": "not_found"}

        # Determine status based on state
        if document.processing_error:
            status = "failed"
            message = document.processing_error
        elif document.raw_text:
            status = "completed"
            message = "Text extraction completed"
        elif document.processing_job_id:
            status = "processing"
            message = "Processing in progress"
            # TODO: Check actual job status from Celery
            # from celery.result import AsyncResult
            # result = AsyncResult(document.processing_job_id)
            # if result.state == "FAILURE":
            #     status = "failed"
            #     message = str(result.info)
        else:
            status = "pending"
            message = "Awaiting processing"

        return {
            "status": status,
            "message": message,
            "document_id": str(doc_id),
            "filename": document.original_filename,
            "has_raw_text": bool(document.raw_text),
            "has_summary": document.summaries.exists(),
            "has_verified_data": document.verified_data.exists(),
        }

    @staticmethod
    def update_raw_text(doc_id: UUID, raw_text: str, highlight_metadata: str = None) -> bool:
        """Update document with extracted text from LLMWhisperer.

        Args:
            doc_id: UUID of the document
            raw_text: Extracted text content
            highlight_metadata: Optional JSON string of highlight coordinates

        Returns:
            bool: True if successful
        """
        try:
            document = AgenticDocument.objects.get(id=doc_id)
            document.raw_text = raw_text
            if highlight_metadata:
                document.highlight_metadata = highlight_metadata
            document.processing_error = None  # Clear any previous errors
            document.save(update_fields=["raw_text", "highlight_metadata", "processing_error"])
            logger.info(f"Updated raw text for document {doc_id}")
            return True
        except AgenticDocument.DoesNotExist:
            logger.error(f"Document {doc_id} not found")
            return False

    @staticmethod
    def mark_processing_error(doc_id: UUID, error_message: str) -> bool:
        """Mark document processing as failed with error message.

        Args:
            doc_id: UUID of the document
            error_message: Error description

        Returns:
            bool: True if successful
        """
        try:
            document = AgenticDocument.objects.get(id=doc_id)
            document.processing_error = error_message
            document.save(update_fields=["processing_error"])
            logger.error(f"Document {doc_id} processing failed: {error_message}")
            return True
        except AgenticDocument.DoesNotExist:
            logger.error(f"Document {doc_id} not found")
            return False

    @staticmethod
    def get_documents_for_summarization(project_id: UUID) -> list:
        """Get all documents ready for summarization.

        Documents must have raw_text but no summary yet.

        Args:
            project_id: UUID of the project

        Returns:
            List of AgenticDocument instances
        """
        documents = AgenticDocument.objects.filter(
            project_id=project_id,
            raw_text__isnull=False,
        ).exclude(
            summaries__isnull=False  # Exclude docs that already have summaries
        )

        return list(documents)

    @staticmethod
    def get_documents_with_verified_data(project_id: UUID) -> list:
        """Get all documents that have verified data (ready for extraction testing).

        Args:
            project_id: UUID of the project

        Returns:
            List of AgenticDocument instances with verified_data
        """
        documents = AgenticDocument.objects.filter(
            project_id=project_id,
            verified_data__isnull=False,
        ).distinct()

        return list(documents)
