"""UN-3749: a partial execution-cache hash must read as a miss, not raise.

``increment_completed_files`` / ``increment_failed_files`` are plain HINCRBYs.
Once the entry has expired (the TTL is 3 h), the next increment recreates the key
with only that counter: no ``workflow_id``, ``execution_id`` or ``status``, and no
TTL. ``get_execution`` passed that straight to ``ExecutionCache(**decoded)``,
which raised ``TypeError``. Every status poll for the execution then failed.

DB-free: ``CacheService`` is mocked with the bytes Redis returns.
"""

from unittest.mock import patch

from workflow_manager.execution.execution_cache_utils import ExecutionCacheUtils
from workflow_manager.workflow_v2.enums import ExecutionStatus

_CACHE = "workflow_manager.execution.execution_cache_utils.CacheService"


def _get(raw):
    with patch(_CACHE) as cache:
        cache.hgetall.return_value = raw
        return ExecutionCacheUtils.get_execution(
            workflow_id="wf-1", execution_id="exec-1"
        )


def test_counter_only_hash_reads_as_a_miss():
    assert _get({b"completed_files": b"1"}) is None


def test_hash_without_ids_but_with_status_is_a_hit():
    # A worker save() after the counter-only key existed adds status (and a
    # TTL) through update_status, but never the ids: the key itself names them.
    entry = _get({b"completed_files": b"2", b"status": b"EXECUTING"})
    assert entry is not None
    assert entry.workflow_id == "wf-1"
    assert entry.execution_id == "exec-1"
    assert ExecutionStatus(entry.status) == ExecutionStatus.EXECUTING


def test_full_hash_is_a_hit():
    entry = _get(
        {
            b"workflow_id": b"wf-1",
            b"execution_id": b"exec-1",
            b"status": b"COMPLETED",
            b"total_files": b"5",
            b"completed_files": b"5",
            b"failed_files": b"0",
        }
    )
    assert ExecutionStatus(entry.status) == ExecutionStatus.COMPLETED


def test_empty_hash_is_a_miss():
    assert _get({}) is None


class TestIncrementsKeepATtl:
    """An increment on an expired entry recreated the key with no TTL, so the
    counter-only hash stayed in Redis for good. Increments now set the TTL too.
    """

    def test_increments_pass_the_entry_ttl(self):
        with patch(_CACHE) as cache:
            ExecutionCacheUtils.increment_completed_files("wf-1", "exec-1")
            ExecutionCacheUtils.increment_failed_files("wf-1", "exec-1")

        assert [c.args for c in cache.hincrby.call_args_list] == [
            ("execution:wf-1:exec-1", "completed_files", 1),
            ("execution:wf-1:exec-1", "failed_files", 1),
        ]
        for c in cache.hincrby.call_args_list:
            assert c.kwargs == {"expire_time": ExecutionCacheUtils.expire_time}

    def test_hincrby_with_ttl_sets_it_in_the_same_transaction(self):
        from utils.cache_service import CacheService

        with patch("utils.cache_service.redis_cache") as redis_cache:
            CacheService.hincrby("k", "f", 1, expire_time=60)

        redis_cache.pipeline.assert_called_once_with(transaction=True)
        pipe = redis_cache.pipeline.return_value
        pipe.hincrby.assert_called_once_with("k", "f", 1)
        pipe.expire.assert_called_once_with("k", 60)
        pipe.execute.assert_called_once()
        redis_cache.hincrby.assert_not_called()

    def test_hincrby_without_ttl_is_unchanged(self):
        from utils.cache_service import CacheService

        with patch("utils.cache_service.redis_cache") as redis_cache:
            CacheService.hincrby("k", "f", 1)

        redis_cache.hincrby.assert_called_once_with("k", "f", 1)
        redis_cache.pipeline.assert_not_called()
