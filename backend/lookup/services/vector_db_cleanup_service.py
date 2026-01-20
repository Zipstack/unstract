"""Vector DB Cleanup Service for Lookup feature.

Provides centralized cleanup operations for removing obsolete
vector DB nodes when reference data is re-indexed, profiles
are changed, or data sources are deleted.
"""

import logging
from typing import Any

from utils.user_context import UserContext

from unstract.sdk1.constants import LogLevel
from unstract.sdk1.vector_db import VectorDB

logger = logging.getLogger(__name__)


class VectorDBCleanupService:
    """Centralized service for vector DB cleanup operations.

    This service handles all vector DB node deletion scenarios:
    - Cleanup on re-indexing (delete old nodes before adding new)
    - Cleanup on profile deletion
    - Cleanup on data source deletion
    - Manual cleanup of stale indexes
    - Cleanup when switching from RAG to full context mode

    Example:
        >>> service = VectorDBCleanupService()
        >>> result = service.cleanup_index_ids(
        ...     index_ids=["doc_id_1", "doc_id_2"], vector_db_instance_id="uuid-of-vector-db"
        ... )
        >>> print(result)
        {'success': True, 'deleted': 2, 'failed': 0, 'errors': []}
    """

    def __init__(self, org_id: str | None = None):
        """Initialize the cleanup service.

        Args:
            org_id: Organization ID for multi-tenancy. If not provided,
                   will be fetched from UserContext.
        """
        self.org_id = org_id or UserContext.get_organization_identifier()

    def _get_vector_db_client(self, vector_db_instance_id: str) -> VectorDB:
        """Get a VectorDB client for the given adapter instance.

        Args:
            vector_db_instance_id: UUID of the vector DB adapter instance

        Returns:
            VectorDB client instance
        """
        from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import (
            PromptIdeBaseTool,
        )

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=self.org_id)
        return VectorDB(tool=util, adapter_instance_id=vector_db_instance_id)

    def cleanup_index_ids(
        self,
        index_ids: list[str],
        vector_db_instance_id: str,
    ) -> dict[str, Any]:
        """Delete specific index IDs from vector DB.

        Args:
            index_ids: List of index IDs (doc_ids) to delete
            vector_db_instance_id: UUID of the vector DB adapter instance

        Returns:
            Dictionary with cleanup results:
                - success: True if all deletions succeeded
                - deleted: Number of successfully deleted indexes
                - failed: Number of failed deletions
                - errors: List of error messages for failed deletions
        """
        if not index_ids:
            logger.debug("No index IDs to clean up")
            return {"success": True, "deleted": 0, "failed": 0, "errors": []}

        if not vector_db_instance_id:
            logger.warning("Cannot cleanup: vector_db_instance_id not provided")
            return {
                "success": False,
                "deleted": 0,
                "failed": len(index_ids),
                "errors": ["vector_db_instance_id not provided"],
            }

        deleted = 0
        failed = 0
        errors = []

        try:
            vector_db = self._get_vector_db_client(vector_db_instance_id)

            for index_id in index_ids:
                try:
                    logger.debug(f"Deleting from VectorDB - index id: {index_id}")
                    vector_db.delete(ref_doc_id=index_id)
                    deleted += 1
                except Exception as e:
                    error_msg = f"Error deleting index {index_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    failed += 1

            logger.info(
                f"Vector DB cleanup completed: {deleted} deleted, {failed} failed"
            )

        except Exception as e:
            error_msg = f"Error initializing vector DB client: {e}"
            logger.error(error_msg, exc_info=True)
            return {
                "success": False,
                "deleted": deleted,
                "failed": len(index_ids) - deleted,
                "errors": [error_msg] + errors,
            }

        return {
            "success": failed == 0,
            "deleted": deleted,
            "failed": failed,
            "errors": errors,
        }

    def cleanup_for_data_source(
        self,
        data_source_id: str,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Clean up all indexes for a data source.

        Args:
            data_source_id: UUID of the LookupDataSource
            profile_id: Optional profile ID to filter by. If not provided,
                       cleans up indexes for all profiles.

        Returns:
            Dictionary with cleanup results
        """
        from lookup.models import LookupIndexManager

        try:
            queryset = LookupIndexManager.objects.filter(data_source_id=data_source_id)
            if profile_id:
                queryset = queryset.filter(profile_manager_id=profile_id)

            total_deleted = 0
            total_failed = 0
            all_errors = []

            for index_manager in queryset:
                if (
                    index_manager.index_ids_history
                    and index_manager.profile_manager
                    and index_manager.profile_manager.vector_store
                ):
                    result = self.cleanup_index_ids(
                        index_ids=index_manager.index_ids_history,
                        vector_db_instance_id=str(
                            index_manager.profile_manager.vector_store.id
                        ),
                    )
                    total_deleted += result["deleted"]
                    total_failed += result["failed"]
                    all_errors.extend(result["errors"])

                    # Clear the history after successful cleanup
                    if result["success"]:
                        index_manager.index_ids_history = []
                        index_manager.raw_index_id = None
                        index_manager.status = {"indexed": False, "cleaned": True}
                        index_manager.save()

            return {
                "success": total_failed == 0,
                "deleted": total_deleted,
                "failed": total_failed,
                "errors": all_errors,
            }

        except Exception as e:
            error_msg = f"Error cleaning up data source {data_source_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "deleted": 0, "failed": 0, "errors": [error_msg]}

    def cleanup_stale_indexes(
        self,
        index_manager,
        keep_current: bool = True,
    ) -> dict[str, Any]:
        """Clean up old indexes, optionally keeping the current one.

        This is useful when re-indexing - delete old nodes but keep
        the most recent one (which will be replaced).

        Args:
            index_manager: LookupIndexManager instance
            keep_current: If True, keeps the current raw_index_id

        Returns:
            Dictionary with cleanup results
        """
        if not index_manager.index_ids_history:
            return {"success": True, "deleted": 0, "failed": 0, "errors": []}

        if (
            not index_manager.profile_manager
            or not index_manager.profile_manager.vector_store
        ):
            logger.warning(
                f"Cannot cleanup stale indexes: missing profile or vector store "
                f"for index manager {index_manager.index_manager_id}"
            )
            return {
                "success": False,
                "deleted": 0,
                "failed": 0,
                "errors": ["Missing profile or vector store"],
            }

        # Determine which IDs to delete
        ids_to_delete = list(index_manager.index_ids_history)
        if keep_current and index_manager.raw_index_id:
            ids_to_delete = [
                id for id in ids_to_delete if id != index_manager.raw_index_id
            ]

        if not ids_to_delete:
            return {"success": True, "deleted": 0, "failed": 0, "errors": []}

        result = self.cleanup_index_ids(
            index_ids=ids_to_delete,
            vector_db_instance_id=str(index_manager.profile_manager.vector_store.id),
        )

        # Update history to remove deleted IDs
        if result["deleted"] > 0:
            remaining_ids = [
                id for id in index_manager.index_ids_history if id not in ids_to_delete
            ]
            index_manager.index_ids_history = remaining_ids
            index_manager.save()

        return result

    def cleanup_for_profile(self, profile_id: str) -> dict[str, Any]:
        """Clean up all indexes created with a specific profile.

        Use this when a profile is being deleted or when switching
        from RAG mode to full context mode.

        Args:
            profile_id: UUID of the LookupProfileManager

        Returns:
            Dictionary with cleanup results
        """
        from lookup.models import LookupIndexManager, LookupProfileManager

        try:
            profile = LookupProfileManager.objects.get(pk=profile_id)
            if not profile.vector_store:
                logger.warning(f"Profile {profile_id} has no vector store configured")
                return {
                    "success": False,
                    "deleted": 0,
                    "failed": 0,
                    "errors": ["Profile has no vector store configured"],
                }

            vector_db_instance_id = str(profile.vector_store.id)
            index_managers = LookupIndexManager.objects.filter(profile_manager=profile)

            total_deleted = 0
            total_failed = 0
            all_errors = []

            for index_manager in index_managers:
                if index_manager.index_ids_history:
                    result = self.cleanup_index_ids(
                        index_ids=index_manager.index_ids_history,
                        vector_db_instance_id=vector_db_instance_id,
                    )
                    total_deleted += result["deleted"]
                    total_failed += result["failed"]
                    all_errors.extend(result["errors"])

                    # Clear the history after cleanup
                    index_manager.index_ids_history = []
                    index_manager.raw_index_id = None
                    index_manager.status = {"indexed": False, "cleaned": True}
                    index_manager.reindex_required = True
                    index_manager.save()

            logger.info(
                f"Profile cleanup completed for {profile_id}: "
                f"{total_deleted} deleted, {total_failed} failed"
            )

            return {
                "success": total_failed == 0,
                "deleted": total_deleted,
                "failed": total_failed,
                "errors": all_errors,
            }

        except LookupProfileManager.DoesNotExist:
            error_msg = f"Profile {profile_id} not found"
            logger.error(error_msg)
            return {"success": False, "deleted": 0, "failed": 0, "errors": [error_msg]}
        except Exception as e:
            error_msg = f"Error cleaning up profile {profile_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return {"success": False, "deleted": 0, "failed": 0, "errors": [error_msg]}

    def cleanup_before_reindex(
        self,
        index_manager,
    ) -> dict[str, Any]:
        """Clean up all existing indexes before re-indexing.

        This should be called before adding a new doc_id during re-indexing
        to ensure old stale data is removed from the vector DB.

        Args:
            index_manager: LookupIndexManager instance

        Returns:
            Dictionary with cleanup results
        """
        if not index_manager.index_ids_history:
            return {"success": True, "deleted": 0, "failed": 0, "errors": []}

        if (
            not index_manager.profile_manager
            or not index_manager.profile_manager.vector_store
        ):
            logger.warning(
                "Cannot cleanup before reindex: missing profile or vector store"
            )
            return {
                "success": False,
                "deleted": 0,
                "failed": 0,
                "errors": ["Missing profile or vector store"],
            }

        logger.info(
            f"Cleaning up {len(index_manager.index_ids_history)} old index(es) "
            f"before re-indexing data source {index_manager.data_source.file_name}"
        )

        result = self.cleanup_index_ids(
            index_ids=index_manager.index_ids_history,
            vector_db_instance_id=str(index_manager.profile_manager.vector_store.id),
        )

        return result
