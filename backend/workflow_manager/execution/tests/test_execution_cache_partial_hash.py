"""UN-3749: a partial execution-cache hash must read as a miss, not raise.

``increment_completed_files`` / ``increment_failed_files`` were plain HINCRBYs.
Once the entry had expired (the TTL is 3 h), the next increment recreated the key
with only that counter: no ``workflow_id``, ``execution_id`` or ``status``, and no
TTL. ``get_execution`` passed that straight to ``ExecutionCache(**decoded)``,
which raised ``TypeError``. Every status poll for the execution then failed.

The increments now never create the hash, and ``get_execution`` reads the
counter-only keys already in Redis as a miss.

DB-free: ``CacheService`` is mocked with the bytes Redis returns.
"""

from unittest.mock import call, patch

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


class TestIncrementsNeverCreateTheHash:
    def test_increments_use_hincrby_if_exists(self):
        with patch(_CACHE) as cache:
            ExecutionCacheUtils.increment_completed_files("wf-1", "exec-1")
            ExecutionCacheUtils.increment_failed_files("wf-1", "exec-1")

        assert cache.method_calls == [
            call.hincrby_if_exists("execution:wf-1:exec-1", "completed_files", 1),
            call.hincrby_if_exists("execution:wf-1:exec-1", "failed_files", 1),
        ]

    def test_hincrby_if_exists_runs_the_guarded_script(self):
        from utils import cache_service

        with patch.object(cache_service, "redis_cache") as redis_cache:
            redis_cache.eval.return_value = 0
            assert not cache_service.CacheService.hincrby_if_exists("k", "f", 1)

        redis_cache.eval.assert_called_once_with(
            cache_service._HINCRBY_IF_EXISTS, 1, "k", "f", 1
        )
        redis_cache.hincrby.assert_not_called()
        script = cache_service._HINCRBY_IF_EXISTS
        assert script.index("EXISTS") < script.index("HINCRBY")
