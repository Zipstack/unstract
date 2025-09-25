"""
Cache for storing API hub headers temporarily during API execution.

This solves the StateStore concurrency issue where headers set in the API view
aren't accessible in Celery tasks due to thread/process isolation.

Uses the same CacheService pattern as ResultCacheUtils for consistency.
"""

import json
import logging
from typing import Any, Dict, Optional

from utils.cache_service import CacheService

logger = logging.getLogger(__name__)


class APIHubHeadersCache:
    """Cache API hub headers using centralized CacheService."""
    
    CACHE_PREFIX = "api_hub_headers:"
    # Shorter TTL for headers - executions typically complete within an hour
    # 2 hours should be sufficient even for large multi-file executions
    CACHE_TTL = 7200  # 2 hours in seconds
    
    def store_headers(self, execution_id: str, headers: Dict[str, Any]) -> bool:
        """
        Store API hub headers for an execution.
        
        Args:
            execution_id: Unique execution identifier
            headers: API hub headers from request
            
        Returns:
            True if stored successfully
        """
        try:
            cache_key = f"{self.CACHE_PREFIX}{execution_id}"
            CacheService.set_key(
                cache_key,
                json.dumps(headers),
                expire=self.CACHE_TTL
            )
            logger.debug(f"Stored API hub headers for execution {execution_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store API hub headers: {e}")
            return False
    
    def get_headers(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve API hub headers for an execution.
        
        Args:
            execution_id: Unique execution identifier
            
        Returns:
            API hub headers dictionary or None
        """
        try:
            cache_key = f"{self.CACHE_PREFIX}{execution_id}"
            cached_data = CacheService.get_key(cache_key)
            
            if cached_data:
                headers = json.loads(cached_data)
                logger.debug(f"Retrieved API hub headers for execution {execution_id}")
                return headers
            
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve API hub headers: {e}")
            return None
    
    def delete_headers(self, execution_id: str) -> bool:
        """
        Delete API hub headers after processing.
        
        Args:
            execution_id: Unique execution identifier
            
        Returns:
            True if deleted successfully
        """
        try:
            cache_key = f"{self.CACHE_PREFIX}{execution_id}"
            CacheService.delete_a_key(cache_key)
            logger.debug(f"Deleted API hub headers for execution {execution_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete API hub headers: {e}")
            return False


# Singleton instance - no initialization needed with CacheService
api_hub_headers_cache = APIHubHeadersCache()