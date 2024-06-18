from utils.cache_service import CacheService


def set_document_indexing(doc_id_key, ttl=1800):
    CacheService.set_key(f'document_indexing:{doc_id_key}', 'started', expire=ttl)

def is_document_indexing(doc_id_key):
    return CacheService.get_key(f'document_indexing:{doc_id_key}') == b'started'

def mark_document_indexed(doc_id_key, doc_id):
    CacheService.set_key(f'document_indexing:{doc_id_key}', doc_id, expire=3600)

def get_indexed_document_id(doc_id_key):
    result = CacheService.get_key(f'document_indexing:{doc_id_key}')
    if result and result != b'started':
        return result
    return None
