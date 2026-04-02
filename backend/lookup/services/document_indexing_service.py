"""Document Indexing Service for Lookup projects.

This service manages indexing status tracking using cache to prevent
duplicate indexing operations and track in-progress indexing.

Based on Prompt Studio's DocumentIndexingService pattern.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


class LookupDocumentIndexingService:
    """Cache-based service to track document indexing status.

    Prevents duplicate indexing and tracks in-progress operations.
    """

    # Cache key format: lookup_indexing:{org_id}:{user_id}:{doc_id_key}
    CACHE_KEY_PREFIX = "lookup_indexing"
    CACHE_TIMEOUT = 3600  # 1 hour

    # Status values
    STATUS_INDEXING = "INDEXING"  # Currently being indexed

    @staticmethod
    def _get_cache_key(org_id: str, user_id: str, doc_id_key: str) -> str:
        """Generate cache key for document indexing status.

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key (hash of indexing parameters)

        Returns:
            Cache key string
        """
        return f"{LookupDocumentIndexingService.CACHE_KEY_PREFIX}:{org_id}:{user_id}:{doc_id_key}"

    @staticmethod
    def is_document_indexing(org_id: str, user_id: str, doc_id_key: str) -> bool:
        """Check if document is currently being indexed.

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key

        Returns:
            True if document is being indexed, False otherwise
        """
        cache_key = LookupDocumentIndexingService._get_cache_key(
            org_id, user_id, doc_id_key
        )
        status = cache.get(cache_key)

        if status == LookupDocumentIndexingService.STATUS_INDEXING:
            logger.debug(f"Document {doc_id_key} is currently being indexed")
            return True

        return False

    @staticmethod
    def set_document_indexing(org_id: str, user_id: str, doc_id_key: str) -> None:
        """Mark document as being indexed.

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key
        """
        cache_key = LookupDocumentIndexingService._get_cache_key(
            org_id, user_id, doc_id_key
        )
        cache.set(
            cache_key,
            LookupDocumentIndexingService.STATUS_INDEXING,
            LookupDocumentIndexingService.CACHE_TIMEOUT,
        )
        logger.debug(f"Marked document {doc_id_key} as being indexed")

    @staticmethod
    def mark_document_indexed(
        org_id: str, user_id: str, doc_id_key: str, doc_id: str
    ) -> None:
        """Mark document as indexed with final doc_id.

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key
            doc_id: Final document ID from indexing service
        """
        cache_key = LookupDocumentIndexingService._get_cache_key(
            org_id, user_id, doc_id_key
        )
        # Store the final doc_id instead of status
        cache.set(cache_key, doc_id, LookupDocumentIndexingService.CACHE_TIMEOUT)
        logger.debug(f"Marked document {doc_id_key} as indexed with ID {doc_id}")

    @staticmethod
    def get_indexed_document_id(org_id: str, user_id: str, doc_id_key: str) -> str | None:
        """Get indexed document ID if already indexed.

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key

        Returns:
            Document ID if indexed, None otherwise
        """
        cache_key = LookupDocumentIndexingService._get_cache_key(
            org_id, user_id, doc_id_key
        )
        cached_value = cache.get(cache_key)

        # Return doc_id only if it's not the "INDEXING" status
        if cached_value and cached_value != LookupDocumentIndexingService.STATUS_INDEXING:
            logger.debug(f"Document {doc_id_key} already indexed with ID {cached_value}")
            return cached_value

        return None

    @staticmethod
    def clear_indexing_status(org_id: str, user_id: str, doc_id_key: str) -> None:
        """Clear indexing status from cache (e.g., on error).

        Args:
            org_id: Organization ID
            user_id: User ID
            doc_id_key: Document ID key
        """
        cache_key = LookupDocumentIndexingService._get_cache_key(
            org_id, user_id, doc_id_key
        )
        cache.delete(cache_key)
        logger.debug(f"Cleared indexing status for document {doc_id_key}")
