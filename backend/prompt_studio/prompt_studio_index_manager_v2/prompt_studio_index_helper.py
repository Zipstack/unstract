import json
import logging

from django.db import transaction
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager

from .models import IndexManager

logger = logging.getLogger(__name__)


class PromptStudioIndexHelper:
    @staticmethod
    def handle_index_manager(
        document_id: str,
        profile_manager: ProfileManager,
        doc_id: str,
        is_summary: bool = False,
    ) -> IndexManager:
        try:

            with transaction.atomic():

                document: DocumentManager = DocumentManager.objects.get(pk=document_id)

                index_id = "raw_index_id"
                if is_summary:
                    index_id = "summarize_index_id"

                args: dict[str, str] = dict()
                args["document_manager"] = document
                args["profile_manager"] = profile_manager

                # Create or get the existing record for this document and
                # profile combo
                index_manager, success = IndexManager.objects.get_or_create(**args)

                if success:
                    logger.info(
                        f"Index manager doc_id: {doc_id} for "
                        f"profile {profile_manager.profile_id} created"
                    )
                else:
                    logger.info(
                        f"Index manager doc_id: {doc_id} for "
                        f"profile {profile_manager.profile_id} updated"
                    )

                index_ids = index_manager.index_ids_history
                if not isinstance(index_ids, list):
                    index_ids_list = json.loads(index_ids) if index_ids else []
                else:
                    index_ids_list = index_ids
                if doc_id not in index_ids:
                    index_ids_list.append(doc_id)

                args[index_id] = doc_id
                args["index_ids_history"] = json.dumps(index_ids_list)

                # Update the record with the index id
                result: IndexManager = IndexManager.objects.filter(
                    index_manager_id=index_manager.index_manager_id
                ).update(**args)
            return result
        except Exception as e:
            transaction.rollback()
            raise IndexingAPIError("Error updating indexing status") from e

    @staticmethod
    def mark_extraction_status(
        document_id: str, profile_manager: ProfileManager, doc_id: str
    ) -> bool:
        """
        Marks the extraction status for a given document.

        Args:
            document_id (str): ID of the document in DocumentManager.
            profile_manager (ProfileManager): ProfileManager instance for context.
            doc_id (str): Unique identifier for the document within extraction status.

        Returns:
            bool: True if the status is successfully updated, False otherwise.

        """
        try:
            with transaction.atomic():
                document = DocumentManager.objects.get(pk=document_id)

                args = {
                    "document_manager": document,
                    "profile_manager": profile_manager,
                }

                index_manager, created = IndexManager.objects.get_or_create(**args)

                index_manager.extraction_status = index_manager.extraction_status or {}

                index_manager.extraction_status[doc_id] = True
                logger.info(f"Index manager {index_manager} {index_manager.index_ids_history}")
                index_manager.save(update_fields=["extraction_status"])

                if created:
                    logger.info(
                        f"IndexManager entry created "
                        f"for document: {document_id} with {doc_id}"
                    )
                else:
                    logger.info(
                        f"Updated extraction status "
                        f"for document: {document_id} with {doc_id}"
                    )
            return True

        except DocumentManager.DoesNotExist:
            logger.error(f"Document with ID {document_id} does not exist.")
            raise IndexingAPIError(
                "Error occured while extracting. Please contact admin."
            )

        except Exception as e:
            logger.error(f"Unexpected error updating extraction status: {e}")
            raise IndexingAPIError(f"Error updating indexing status {str(e)}") from e

    @staticmethod
    def check_extraction_status(
        document_id: str, profile_manager: ProfileManager, doc_id: str
    ) -> bool:
        """
        Checks if the extraction status is already marked as complete
        for the given document and doc_id.

        Args:
            document_id (str): ID of the document in DocumentManager.
            profile_manager (ProfileManager): ProfileManager instance for context.
            doc_id (str): Unique identifier for the document within extraction status.

        Returns:
            bool: True if extraction is complete, False otherwise.
        """
        try:
            index_manager = IndexManager.objects.filter(
                document_manager=document_id, profile_manager=profile_manager
            ).first()

            if not index_manager:
                logger.info(f"No IndexManager record found for document: {document_id}")
                return False

            extraction_status = index_manager.extraction_status or {}
            is_extracted = extraction_status.get(doc_id, False)

            if is_extracted:
                logger.info(
                    f"Extraction is already marked as complete "
                    f"for document: {document_id} with {doc_id}"
                )
            else:
                logger.info(
                    f"Extraction is NOT yet marked as complete "
                    f"for document: {document_id} with {doc_id}"
                )

            return is_extracted

        except Exception as e:
            logger.error(f"Unexpected error while checking extraction status: {e}")
            raise IndexingAPIError(f"Error checking extraction status {str(e)}") from e
