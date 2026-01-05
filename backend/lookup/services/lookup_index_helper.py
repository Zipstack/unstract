"""Helper service for Lookup IndexManager operations.

Based on Prompt Studio's PromptStudioIndexHelper pattern.
"""

import logging

from django.db import transaction

from lookup.models import LookupIndexManager

logger = logging.getLogger(__name__)


class LookupIndexHelper:
    """Helper class for LookupIndexManager CRUD operations."""

    @staticmethod
    @transaction.atomic
    def handle_index_manager(
        data_source_id: str,
        profile_manager,
        doc_id: str,
    ) -> LookupIndexManager:
        """Create or update LookupIndexManager with doc_id.

        Args:
            data_source_id: UUID of the LookupDataSource
            profile_manager: LookupProfileManager instance
            doc_id: Document ID returned from indexing service

        Returns:
            LookupIndexManager instance
        """
        from lookup.models import LookupDataSource

        try:
            data_source = LookupDataSource.objects.get(pk=data_source_id)

            # Get or create index manager for this data source + profile combination
            index_manager, created = LookupIndexManager.objects.get_or_create(
                data_source=data_source,
                profile_manager=profile_manager,
                defaults={
                    "raw_index_id": doc_id,
                    "index_ids_history": [doc_id],
                    "status": {"indexed": True, "error": None},
                },
            )

            if not created:
                # Update existing index manager
                index_manager.raw_index_id = doc_id

                # Add to history if not already present
                if doc_id not in index_manager.index_ids_history:
                    index_manager.index_ids_history.append(doc_id)

                # Update status
                index_manager.status = {"indexed": True, "error": None}

                index_manager.save()
                logger.debug(f"Updated index manager for data source {data_source_id}")
            else:
                logger.debug(f"Created index manager for data source {data_source_id}")

            return index_manager

        except LookupDataSource.DoesNotExist:
            logger.error(f"Data source {data_source_id} not found")
            raise
        except Exception as e:
            logger.error(f"Error handling index manager: {e}", exc_info=True)
            raise

    @staticmethod
    def check_extraction_status(
        data_source_id: str,
        profile_manager,
        x2text_config_hash: str,
        enable_highlight: bool = False,
    ) -> bool:
        """Check if extraction already completed for this configuration.

        Args:
            data_source_id: UUID of the LookupDataSource
            profile_manager: LookupProfileManager instance
            x2text_config_hash: Hash of X2Text adapter configuration
            enable_highlight: Whether highlighting is enabled

        Returns:
            True if extraction completed with same settings, False otherwise
        """
        try:
            index_manager = LookupIndexManager.objects.get(
                data_source_id=data_source_id, profile_manager=profile_manager
            )

            extraction_status = index_manager.extraction_status.get(
                x2text_config_hash, {}
            )

            if not extraction_status.get("extracted", False):
                return False

            # Check if highlight setting matches
            stored_highlight = extraction_status.get("enable_highlight", False)
            if stored_highlight != enable_highlight:
                logger.debug(
                    f"Highlight setting mismatch: stored={stored_highlight}, "
                    f"requested={enable_highlight}"
                )
                return False

            logger.debug(f"Extraction already completed for {x2text_config_hash}")
            return True

        except LookupIndexManager.DoesNotExist:
            logger.debug(f"No index manager found for data source {data_source_id}")
            return False
        except Exception as e:
            logger.error(f"Error checking extraction status: {e}", exc_info=True)
            return False

    @staticmethod
    @transaction.atomic
    def mark_extraction_status(
        data_source_id: str,
        profile_manager,
        x2text_config_hash: str,
        enable_highlight: bool = False,
        extracted: bool = True,
        error_message: str = None,
    ) -> bool:
        """Mark extraction success or failure in IndexManager.

        Args:
            data_source_id: UUID of the LookupDataSource
            profile_manager: LookupProfileManager instance
            x2text_config_hash: Hash of X2Text adapter configuration
            enable_highlight: Whether highlighting is enabled
            extracted: Whether extraction succeeded
            error_message: Error message if extraction failed

        Returns:
            True if status marked successfully, False otherwise
        """
        from lookup.models import LookupDataSource

        try:
            data_source = LookupDataSource.objects.get(pk=data_source_id)

            # Get or create index manager
            index_manager, created = LookupIndexManager.objects.get_or_create(
                data_source=data_source,
                profile_manager=profile_manager,
                defaults={"extraction_status": {}, "status": {}},
            )

            # Update extraction status for this configuration
            index_manager.extraction_status[x2text_config_hash] = {
                "extracted": extracted,
                "enable_highlight": enable_highlight,
                "error": error_message,
            }

            # Also update overall status
            if extracted:
                index_manager.status["extracted"] = True
                index_manager.status["error"] = None
            else:
                index_manager.status["extracted"] = False
                index_manager.status["error"] = error_message

            index_manager.save()

            status_text = "success" if extracted else "failure"
            logger.debug(
                f"Marked extraction {status_text} for data source {data_source_id}, "
                f"config {x2text_config_hash}"
            )

            return True

        except LookupDataSource.DoesNotExist:
            logger.error(f"Data source {data_source_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error marking extraction status: {e}", exc_info=True)
            return False
