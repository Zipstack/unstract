from django.conf import settings
from utils.cache_service import CacheService

from prompt_studio.prompt_studio_core_v2.constants import IndexingStatus


class DocumentIndexingService:
    CACHE_PREFIX = "document_indexing:"

    @classmethod
    def set_document_indexing(cls, org_id: str, user_id: str, doc_id_key: str) -> None:
        CacheService.set_key(
            cls._cache_key(org_id, user_id, doc_id_key),
            IndexingStatus.STARTED_STATUS.value,
            expire=settings.INDEXING_FLAG_TTL,
        )

    @classmethod
    def is_document_indexing(cls, org_id: str, user_id: str, doc_id_key: str) -> bool:
        return (
            CacheService.get_key(cls._cache_key(org_id, user_id, doc_id_key))
            == IndexingStatus.STARTED_STATUS.value
        )

    @classmethod
    def mark_document_indexed(
        cls, org_id: str, user_id: str, doc_id_key: str, doc_id: str
    ) -> None:
        CacheService.set_key(
            cls._cache_key(org_id, user_id, doc_id_key),
            doc_id,
            expire=settings.INDEXING_FLAG_TTL,
        )

    @classmethod
    def get_indexed_document_id(
        cls, org_id: str, user_id: str, doc_id_key: str
    ) -> str | None:
        result = CacheService.get_key(cls._cache_key(org_id, user_id, doc_id_key))
        if result and result != IndexingStatus.STARTED_STATUS.value:
            return result
        return None

    @classmethod
    def remove_document_indexing(cls, org_id: str, user_id: str, doc_id_key: str) -> None:
        CacheService.delete_a_key(cls._cache_key(org_id, user_id, doc_id_key))

    @classmethod
    def _cache_key(cls, org_id: str, user_id: str, doc_id_key: str) -> str:
        return f"{cls.CACHE_PREFIX}{org_id}:{user_id}:{doc_id_key}"
