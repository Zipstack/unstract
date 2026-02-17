"""
Tests for LLM Response Cache implementation.

This module tests the LLMResponseCache class including basic operations,
TTL expiration, cache key generation, and cache management functionality.
"""

import time
from unittest.mock import patch

import pytest

from lookup.services.llm_cache import LLMResponseCache


class TestLLMResponseCache:
    """Test cases for LLMResponseCache class."""

    @pytest.fixture
    def cache(self):
        """Create a fresh cache instance for each test."""
        return LLMResponseCache(ttl_hours=1)

    @pytest.fixture
    def short_ttl_cache(self):
        """Create cache with very short TTL for expiration testing."""
        # 0.001 hours = 3.6 seconds
        return LLMResponseCache(ttl_hours=0.001)

    # ========== Basic Operations Tests ==========

    def test_set_stores_value(self, cache):
        """Test that set() correctly stores a value."""
        cache.set("test_key", "test_response")
        assert "test_key" in cache.cache
        stored_value, _ = cache.cache["test_key"]
        assert stored_value == "test_response"

    def test_get_retrieves_stored_value(self, cache):
        """Test that get() retrieves a stored value."""
        cache.set("test_key", "test_response")
        result = cache.get("test_key")
        assert result == "test_response"

    def test_get_returns_none_for_missing_key(self, cache):
        """Test that get() returns None for non-existent key."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_set_overwrites_existing_value(self, cache):
        """Test that set() overwrites existing values."""
        cache.set("test_key", "first_response")
        cache.set("test_key", "second_response")
        result = cache.get("test_key")
        assert result == "second_response"

    # ========== TTL Expiration Tests ==========

    def test_get_returns_value_before_expiration(self, cache):
        """Test that get() returns value before TTL expiration."""
        cache.set("test_key", "test_response")
        # Should still be valid after immediate retrieval
        result = cache.get("test_key")
        assert result == "test_response"

    def test_get_returns_none_after_expiration(self, short_ttl_cache):
        """Test that get() returns None after TTL expiration."""
        short_ttl_cache.set("test_key", "test_response")
        # Wait for expiration (TTL is 3.6 seconds)
        time.sleep(4)
        result = short_ttl_cache.get("test_key")
        assert result is None

    def test_expired_entry_removed_on_access(self, short_ttl_cache):
        """Test that expired entries are lazily removed on access."""
        short_ttl_cache.set("test_key", "test_response")
        assert "test_key" in short_ttl_cache.cache

        # Wait for expiration
        time.sleep(4)
        result = short_ttl_cache.get("test_key")

        assert result is None
        assert "test_key" not in short_ttl_cache.cache

    @patch('time.time')
    def test_ttl_calculation(self, mock_time, cache):
        """Test correct TTL calculation using mocked time."""
        # Set initial time
        mock_time.return_value = 1000.0
        cache.set("test_key", "test_response")

        # Verify expiry is set correctly (1 hour = 3600 seconds)
        _, expiry = cache.cache["test_key"]
        assert expiry == 4600.0  # 1000 + 3600

        # Move time forward but not past expiry
        mock_time.return_value = 4599.0
        assert cache.get("test_key") == "test_response"

        # Move time past expiry
        mock_time.return_value = 4601.0
        assert cache.get("test_key") is None

    # ========== Cache Key Generation Tests ==========

    def test_cache_key_generation_deterministic(self, cache):
        """Test that same inputs generate same cache key."""
        prompt = "Match vendor {{input_data.vendor}}"
        ref_data = "Slack\nGoogle\nMicrosoft"

        key1 = cache.generate_cache_key(prompt, ref_data)
        key2 = cache.generate_cache_key(prompt, ref_data)

        assert key1 == key2

    def test_different_prompt_different_key(self, cache):
        """Test that different prompts generate different keys."""
        ref_data = "Slack\nGoogle\nMicrosoft"

        key1 = cache.generate_cache_key("Prompt 1", ref_data)
        key2 = cache.generate_cache_key("Prompt 2", ref_data)

        assert key1 != key2

    def test_different_ref_data_different_key(self, cache):
        """Test that different reference data generates different keys."""
        prompt = "Match vendor {{input_data.vendor}}"

        key1 = cache.generate_cache_key(prompt, "Slack\nGoogle")
        key2 = cache.generate_cache_key(prompt, "Slack\nMicrosoft")

        assert key1 != key2

    def test_cache_key_is_valid_sha256(self, cache):
        """Test that cache key is valid SHA256 hex (64 characters)."""
        key = cache.generate_cache_key("test prompt", "test ref data")

        assert len(key) == 64
        assert all(c in '0123456789abcdef' for c in key)

    def test_cache_key_handles_unicode(self, cache):
        """Test cache key generation with Unicode characters."""
        prompt = "Match vendor: Müller GmbH"
        ref_data = "Zürich AG\n北京公司\n東京株式会社"

        key = cache.generate_cache_key(prompt, ref_data)
        assert len(key) == 64

    # ========== Cache Management Tests ==========

    def test_invalidate_removes_specific_key(self, cache):
        """Test that invalidate() removes specific key."""
        cache.set("key1", "response1")
        cache.set("key2", "response2")

        result = cache.invalidate("key1")

        assert result is True
        assert cache.get("key1") is None
        assert cache.get("key2") == "response2"

    def test_invalidate_returns_false_for_missing_key(self, cache):
        """Test that invalidate() returns False for non-existent key."""
        result = cache.invalidate("nonexistent_key")
        assert result is False

    def test_invalidate_all_clears_cache(self, cache):
        """Test that invalidate_all() clears entire cache."""
        cache.set("key1", "response1")
        cache.set("key2", "response2")
        cache.set("key3", "response3")

        count = cache.invalidate_all()

        assert count == 3
        assert len(cache.cache) == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_invalidate_all_returns_zero_for_empty_cache(self, cache):
        """Test that invalidate_all() returns 0 for empty cache."""
        count = cache.invalidate_all()
        assert count == 0

    # ========== Statistics Tests ==========

    def test_get_stats_with_valid_entries(self, cache):
        """Test get_stats() with all valid entries."""
        cache.set("key1", "response1")
        cache.set("key2", "response2")

        stats = cache.get_stats()

        assert stats['total'] == 2
        assert stats['valid'] == 2
        assert stats['expired'] == 0

    @patch('time.time')
    def test_get_stats_with_mixed_entries(self, mock_time, cache):
        """Test get_stats() with mix of valid and expired entries."""
        # Set initial time
        mock_time.return_value = 1000.0

        cache.set("key1", "response1")
        cache.set("key2", "response2")

        # Manually expire one entry
        cache.cache["key1"] = ("response1", 999.0)  # Already expired

        stats = cache.get_stats()

        assert stats['total'] == 2
        assert stats['valid'] == 1
        assert stats['expired'] == 1

    def test_get_stats_empty_cache(self, cache):
        """Test get_stats() with empty cache."""
        stats = cache.get_stats()

        assert stats['total'] == 0
        assert stats['valid'] == 0
        assert stats['expired'] == 0

    # ========== Cleanup Tests ==========

    @patch('time.time')
    def test_cleanup_expired_removes_expired_entries(self, mock_time, cache):
        """Test cleanup_expired() removes only expired entries."""
        # Set initial time
        mock_time.return_value = 1000.0

        cache.set("key1", "response1")
        cache.set("key2", "response2")
        cache.set("key3", "response3")

        # Manually expire two entries
        cache.cache["key1"] = ("response1", 999.0)  # Expired
        cache.cache["key2"] = ("response2", 999.0)  # Expired
        # key3 remains valid (expiry at 4600.0)

        removed_count = cache.cleanup_expired()

        assert removed_count == 2
        assert len(cache.cache) == 1
        assert "key3" in cache.cache
        assert "key1" not in cache.cache
        assert "key2" not in cache.cache

    def test_cleanup_expired_empty_cache(self, cache):
        """Test cleanup_expired() with empty cache."""
        removed_count = cache.cleanup_expired()
        assert removed_count == 0

    def test_cleanup_expired_no_expired_entries(self, cache):
        """Test cleanup_expired() when no entries are expired."""
        cache.set("key1", "response1")
        cache.set("key2", "response2")

        removed_count = cache.cleanup_expired()

        assert removed_count == 0
        assert len(cache.cache) == 2

    # ========== Integration Tests ==========

    def test_end_to_end_caching_workflow(self, cache):
        """Test complete caching workflow."""
        # Generate cache key
        prompt = "Match vendor Slack India"
        ref_data = "Slack\nGoogle\nMicrosoft"
        cache_key = cache.generate_cache_key(prompt, ref_data)

        # Initially no cached value
        assert cache.get(cache_key) is None

        # Store response
        llm_response = '{"canonical_vendor": "Slack", "confidence": 0.92}'
        cache.set(cache_key, llm_response)

        # Retrieve cached value
        cached = cache.get(cache_key)
        assert cached == llm_response

        # Check stats
        stats = cache.get_stats()
        assert stats['valid'] == 1

        # Invalidate
        removed = cache.invalidate(cache_key)
        assert removed is True
        assert cache.get(cache_key) is None

    def test_concurrent_operations(self, cache):
        """Test cache handles multiple operations correctly."""
        # Add multiple entries
        for i in range(10):
            key = f"key_{i}"
            response = f"response_{i}"
            cache.set(key, response)

        # Verify all entries exist
        for i in range(10):
            key = f"key_{i}"
            assert cache.get(key) == f"response_{i}"

        # Invalidate some entries
        for i in range(0, 10, 2):  # Even indices
            cache.invalidate(f"key_{i}")

        # Verify correct entries remain
        for i in range(10):
            key = f"key_{i}"
            if i % 2 == 0:
                assert cache.get(key) is None
            else:
                assert cache.get(key) == f"response_{i}"

        # Clear all
        count = cache.invalidate_all()
        assert count == 5  # Only odd indices remained
