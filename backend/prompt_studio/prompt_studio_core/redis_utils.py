from typing import Optional

from django.conf import settings
from utils.cache_service import CacheService


def set_document_indexing(doc_id_key: str, ttl: int = 1800) -> None:
    CacheService.set_key(f"document_indexing:{doc_id_key}", "started", expire=ttl)


def is_document_indexing(doc_id_key: str) -> bool:
    return CacheService.get_key(f"document_indexing:{doc_id_key}") == b"started"


def mark_document_indexed(doc_id_key: str, doc_id: str) -> None:
    CacheService.set_key(
        f"document_indexing:{doc_id_key}", doc_id, expire=settings.INDEXING_FLAG_TTL
    )


def get_indexed_document_id(doc_id_key: str) -> Optional[str]:
    result = CacheService.get_key(f"document_indexing:{doc_id_key}")
    if result and result != b"started":
        return result
    return None


def remove_document_indexing(doc_id_key: str) -> None:
    CacheService.delete_a_key(f"document_indexing:{doc_id_key}")
