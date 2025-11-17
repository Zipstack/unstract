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
        document_id: str,
        profile_manager: ProfileManager,
        x2text_config_hash: str,
        enable_highlight: bool,
        extracted: bool = True,
        error_message: str | None = None,
    ) -> bool:
        """Marks the extraction status for a given document.

        Uses x2text_config_hash (hash of X2Text config metadata) as the key.
        Handles both successful and failed extractions.

        Args:
            document_id (str): ID of the document in DocumentManager.
            profile_manager (ProfileManager): ProfileManager instance for context.
            x2text_config_hash (str): Hash of X2Text config metadata.
            enable_highlight (bool): Whether highlight metadata was used/attempted.
            extracted (bool): True for success, False for failure. Defaults to True.
            error_message (str | None): Error message if extraction failed.

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

                # Build extraction status data
                status_data = {
                    "extracted": extracted,
                    "enable_highlight": enable_highlight,
                }

                # Add error message if extraction failed
                if not extracted and error_message:
                    status_data["error"] = error_message

                defaults = {"extraction_status": {x2text_config_hash: status_data}}

                index_manager, created = IndexManager.objects.update_or_create(
                    **args,
                    defaults=defaults,
                )

                logger.info(
                    f"Index manager {index_manager} {index_manager.index_ids_history}"
                )

                if extracted:
                    if created:
                        logger.info(
                            f"IndexManager entry created with SUCCESS "
                            f"for document: {document_id} "
                            f"with x2text_config_hash: {x2text_config_hash}"
                        )
                    else:
                        logger.info(
                            f"Extraction SUCCESS for document: {document_id} "
                            f"with x2text_config_hash: {x2text_config_hash}"
                        )
                else:
                    logger.error(
                        f"Extraction FAILED for document: {document_id} "
                        f"with x2text_config_hash: {x2text_config_hash}. "
                        f"Error: {error_message}"
                    )

            return True

        except DocumentManager.DoesNotExist:
            logger.error(f"Document with ID {document_id} does not exist.")
            return False

        except Exception as e:
            logger.exception(
                f"Unexpected error marking extraction status for document {document_id}: {e}"
            )
            return False

    @staticmethod
    def check_extraction_status(
        document_id: str,
        profile_manager: ProfileManager,
        x2text_config_hash: str,
        enable_highlight: bool,
    ) -> bool:
        """Checks if the extraction status is already marked as complete.

        Uses x2text_config_hash (hash of X2Text config metadata) as the key.
        Also validates that enable_highlight setting matches.

        Args:
            document_id (str): ID of the document in DocumentManager.
            profile_manager (ProfileManager): ProfileManager instance for context.
            x2text_config_hash (str): Hash of X2Text config metadata.
            enable_highlight (bool): Whether highlight metadata is required.

        Returns:
            bool: True if extraction is complete with matching settings, False otherwise.
        """
        try:
            index_manager = IndexManager.objects.filter(
                document_manager=document_id, profile_manager=profile_manager
            ).first()

            if not index_manager:
                logger.info(f"No IndexManager record found for document: {document_id}")
                return False

            extraction_status = index_manager.extraction_status or {}
            status_entry = extraction_status.get(x2text_config_hash)

            if not status_entry:
                logger.info(
                    f"Extraction NOT complete for document: {document_id} "
                    f"with x2text_config_hash: {x2text_config_hash}"
                )
                return False

            # {"extracted": True/False, "enable_highlight": bool, "error": str (optional)}
            is_extracted = status_entry.get("extracted", False)
            stored_highlight = status_entry.get("enable_highlight", False)

            # Check if previous extraction failed
            if not is_extracted:
                error_msg = status_entry.get("error", "Unknown error")
                logger.info(
                    f"Previous extraction FAILED for {x2text_config_hash}. "
                    f"Error: {error_msg}. Will retry extraction."
                )
                return False  # Allow retry

            if is_extracted and stored_highlight == enable_highlight:
                logger.info(
                    f"Extraction already complete for document: {document_id} "
                    f"with x2text_config_hash: {x2text_config_hash} "
                    f"(highlight={enable_highlight})"
                )
                return True
            elif is_extracted and stored_highlight != enable_highlight:
                logger.info(
                    f"Extraction exists but highlight mismatch for {x2text_config_hash}. "
                    f"Stored: {stored_highlight}, Requested: {enable_highlight}. "
                    f"Re-extraction needed."
                )
                return False
            else:
                logger.info(f"Extraction NOT complete for document: {document_id}")
                return False

        except Exception as e:
            logger.error(f"Unexpected error while checking extraction status: {e}")
            raise IndexingAPIError(f"Error checking extraction status {str(e)}") from e
