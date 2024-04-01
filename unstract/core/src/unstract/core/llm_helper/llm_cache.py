import hashlib
import logging
import os

import redis

logger = logging.getLogger(__name__)


class LLMCache:
    def __init__(self, cache_key_prefix: str) -> None:
        redis_host = os.environ.get("REDIS_HOST")
        redis_port = os.environ.get("REDIS_PORT")
        if redis_host is None or redis_port is None:
            raise RuntimeError(
                "REDIS_HOST or REDIS_PORT environment variable not set"
            )
        redis_password = os.environ.get("REDIS_PASSWORD", None)
        if redis_password and (
            redis_password == "" or redis_password.lower() == "none"
        ):
            redis_password = None
        self.llm_cache = redis.Redis(
            host=redis_host, port=int(redis_port), password=redis_password
        )
        self.cache_key_prefix = cache_key_prefix

    def __del__(self):
        if self.llm_cache:
            self.llm_cache.close()

    def _get_cache_key(self, seed: str) -> str:
        _hash = hashlib.sha1()
        _hash.update(seed.encode("utf-8"))
        hash_hex = _hash.hexdigest()
        return self.cache_key_prefix + str(hash_hex)

    def get(self, key: str) -> str:
        response = ""
        try:
            response_bin = self.llm_cache.get(key)
            if response_bin is not None:
                logger.info("Cache hit")
                response = response_bin.decode("utf-8")
            else:
                logger.info("Cache miss")
        except Exception as e:
            logger.warning(f"Error loading {key} from cache: {e}")
        return response

    def set(self, key: str, value: str) -> None:
        try:
            self.llm_cache.set(key, value)
        except Exception as e:
            logger.warning(f"Error saving {key} to cache: {e}")

    def delete(self, *keys: str) -> int:
        """Deletes keys from the cache.

        Args:
            keys (str): Variable number of keys to delete

        Returns:
            int: Number of keys deleted, -1 if it fails
        """
        deleted_count = 0
        try:
            deleted_count = self.llm_cache.delete(*keys)
            logger.info(f"Deleted {deleted_count} keys from the cache")
        except Exception:
            logger.warning(f"Error deleting {keys} from cache")
            return -1
        return deleted_count

    def get_for_prompt(self, prompt: str) -> str:
        """Gets the cached value for a prompt It hashes the prompt and prefixes
        the key with `cache_key_prefix`.

        Args:
            prompt (str): Prompt to retrieve value for

        Returns:
            str: Cached response
        """
        key = self._get_cache_key(seed=prompt)
        return self.get(key=key)

    def set_for_prompt(self, prompt: str, response: str) -> None:
        """Sets response from LLM in cache.

        Args:
            prompt (str): Used to determine cache key
            response (str): Response to be cached

        Returns:
            None
        """
        key = self._get_cache_key(seed=prompt)
        return self.set(key=key, value=response)

    def clear_by_prefix(self) -> int:
        """Used to clear the cache by prefix. Prefix is set when instance is
        created. Iterates and deletes each key matching prefix.

        Returns:
            int: Number of keys deleted, -1 if it fails
        """
        logger.info(f"Clearing cache with prefix: {self.cache_key_prefix}")
        keys_to_delete = [
            key
            for key in self.llm_cache.scan_iter(
                match=self.cache_key_prefix + "*"
            )
        ]
        if keys_to_delete:
            return self.delete(*keys_to_delete)
        else:
            return 0
