"""
Tests for Redis cache integration.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.conf import settings

from ...integrations.redis_cache import RedisLLMCache


class RedisLLMCacheTest(TestCase):
    """Test cases for RedisLLMCache."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock Redis availability
        self.redis_patcher = patch('lookup.integrations.redis_cache.REDIS_AVAILABLE', True)
        self.redis_patcher.start()

        # Mock Redis client
        self.redis_client_patcher = patch('lookup.integrations.redis_cache.redis.Redis')
        self.mock_redis_class = self.redis_client_patcher.start()

        # Create mock Redis instance
        self.mock_redis = MagicMock()
        self.mock_redis_class.return_value = self.mock_redis
        self.mock_redis.ping.return_value = True

        # Mock settings
        self.settings_patcher = patch.multiple(
            settings,
            REDIS_HOST='localhost',
            REDIS_PORT=6379,
            REDIS_CACHE_DB=1,
            REDIS_PASSWORD='test-pass'
        )
        self.settings_patcher.start()

        # Initialize cache
        self.cache = RedisLLMCache(ttl_hours=24)

    def tearDown(self):
        """Clean up patches."""
        self.redis_patcher.stop()
        self.redis_client_patcher.stop()
        self.settings_patcher.stop()

    def test_initialization_with_redis(self):
        """Test cache initialization with Redis available."""
        self.assertIsNotNone(self.cache.redis_client)
        self.mock_redis.ping.assert_called_once()
        self.assertEqual(self.cache.ttl_seconds, 24 * 3600)
        self.assertEqual(self.cache.key_prefix, "lookup:llm:")

    def test_initialization_without_redis(self):
        """Test cache initialization when Redis unavailable."""
        # Mock Redis connection failure
        self.mock_redis.ping.side_effect = Exception("Connection failed")

        # Reinitialize cache
        cache = RedisLLMCache(fallback_to_memory=True)

        # Should fall back to memory cache
        self.assertIsNone(cache.redis_client)
        self.assertIsNotNone(cache.memory_cache)

    def test_generate_cache_key(self):
        """Test cache key generation."""
        prompt = "Test prompt"
        reference = "Reference data"

        key = self.cache.generate_cache_key(prompt, reference)

        # Should be prefixed and hashed
        self.assertTrue(key.startswith("lookup:llm:"))
        self.assertEqual(len(key), len("lookup:llm:") + 64)  # SHA256 hex length

    def test_set_and_get(self):
        """Test setting and getting cache values."""
        # Test set
        key = "lookup:llm:test-key"
        value = '{"result": "test"}'

        result = self.cache.set(key, value)
        self.assertTrue(result)

        # Verify Redis setex called
        self.mock_redis.setex.assert_called_once_with(
            name=key,
            time=24 * 3600,
            value=value
        )

        # Test get
        self.mock_redis.get.return_value = value
        retrieved = self.cache.get(key)

        self.assertEqual(retrieved, value)
        self.mock_redis.get.assert_called_once_with(key)

    def test_get_cache_miss(self):
        """Test cache miss."""
        self.mock_redis.get.return_value = None

        result = self.cache.get("lookup:llm:nonexistent")

        self.assertIsNone(result)

    def test_delete(self):
        """Test deleting cache entries."""
        key = "lookup:llm:test-key"
        self.mock_redis.delete.return_value = 1

        result = self.cache.delete(key)

        self.assertTrue(result)
        self.mock_redis.delete.assert_called_once_with(key)

    def test_delete_nonexistent(self):
        """Test deleting non-existent entry."""
        self.mock_redis.delete.return_value = 0

        result = self.cache.delete("lookup:llm:nonexistent")

        # Redis returns 0 for non-existent keys
        self.assertFalse(result)

    def test_clear_pattern(self):
        """Test clearing entries by pattern."""
        # Mock SCAN operation
        self.mock_redis.scan.side_effect = [
            (100, ["lookup:llm:project1:key1", "lookup:llm:project1:key2"]),
            (0, ["lookup:llm:project1:key3"])
        ]
        self.mock_redis.delete.return_value = 3

        count = self.cache.clear_pattern("lookup:llm:project1:*")

        self.assertEqual(count, 3)
        self.mock_redis.delete.assert_called()

    def test_fallback_to_memory_cache(self):
        """Test fallback to memory cache when Redis fails."""
        # Make Redis operations fail
        from redis.exceptions import RedisError
        self.mock_redis.get.side_effect = RedisError("Connection lost")
        self.mock_redis.setex.side_effect = RedisError("Connection lost")

        # Cache should have memory fallback
        self.assertIsNotNone(self.cache.memory_cache)

        # Test set with fallback
        key = "lookup:llm:test"
        value = "test-value"

        result = self.cache.set(key, value)
        self.assertTrue(result)  # Should succeed with memory cache

        # Test get with fallback
        retrieved = self.cache.get(key)
        # Memory cache uses key without prefix
        self.assertEqual(retrieved, value)

    def test_get_stats(self):
        """Test getting cache statistics."""
        # Mock Redis info
        self.mock_redis.info.side_effect = [
            {  # stats info
                'total_connections_received': 100,
                'keyspace_hits': 80,
                'keyspace_misses': 20
            },
            {  # keyspace info
                'db1': {'keys': 50, 'expires': 45}
            }
        ]

        stats = self.cache.get_stats()

        # Verify stats structure
        self.assertEqual(stats['backend'], 'redis')
        self.assertEqual(stats['ttl_hours'], 24)
        self.assertIn('redis', stats)
        self.assertEqual(stats['redis']['keyspace_hits'], 80)
        self.assertEqual(stats['redis']['hit_rate'], 0.8)

    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        # Redis handles expiration automatically
        count = self.cache.cleanup_expired()

        # Should return 0 for Redis (automatic expiry)
        self.assertEqual(count, 0)

    def test_warmup(self):
        """Test cache warmup."""
        project_id = "test-project"
        preload_data = {
            "prompt1": "response1",
            "prompt2": "response2"
        }

        count = self.cache.warmup(project_id, preload_data)

        self.assertEqual(count, 2)
        self.assertEqual(self.mock_redis.setex.call_count, 2)

    def test_custom_ttl(self):
        """Test setting cache with custom TTL."""
        key = "lookup:llm:test"
        value = "test-value"
        custom_ttl = 3600  # 1 hour

        self.cache.set(key, value, ttl=custom_ttl)

        # Verify custom TTL was used
        self.mock_redis.setex.assert_called_with(
            name=key,
            time=custom_ttl,
            value=value
        )

    def test_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        # Test with hits and misses
        rate = self.cache._calculate_hit_rate(80, 20)
        self.assertEqual(rate, 0.8)

        # Test with no data
        rate = self.cache._calculate_hit_rate(0, 0)
        self.assertEqual(rate, 0.0)

    def test_pattern_matching(self):
        """Test pattern matching for memory cache."""
        # Test exact match
        self.assertTrue(self.cache._match_pattern("key1", "key1"))

        # Test wildcard match
        self.assertTrue(self.cache._match_pattern("project:key1", "project:*"))
        self.assertTrue(self.cache._match_pattern("project:subkey:value", "project:*:value"))

        # Test non-match
        self.assertFalse(self.cache._match_pattern("other:key", "project:*"))


class RedisUnavailableTest(TestCase):
    """Test cases when Redis is not available."""

    def setUp(self):
        """Set up test without Redis."""
        # Mock Redis as unavailable
        self.redis_patcher = patch('lookup.integrations.redis_cache.REDIS_AVAILABLE', False)
        self.redis_patcher.start()

    def tearDown(self):
        """Clean up patches."""
        self.redis_patcher.stop()

    def test_initialization_without_redis_package(self):
        """Test when redis package is not installed."""
        cache = RedisLLMCache()

        # Should initialize without Redis
        self.assertIsNone(cache.redis_client)
        self.assertIsNotNone(cache.memory_cache)

        # Should still be functional with memory cache
        key = cache.generate_cache_key("test", "data")
        cache.set(key, "value")
        self.assertEqual(cache.get(key), "value")
