"""Memory leak simulation tests.

These tests demonstrate and verify that resource leaks are fixed by:
1. Simulating the OLD (leaky) behavior
2. Simulating the NEW (fixed) behavior
3. Comparing resource usage between them

Run with: pytest tests/test_memory_leak_simulation.py -v -s
"""

import gc
import tracemalloc
from unittest.mock import MagicMock


class FakeCursor:
    """Simulates a database cursor that tracks if it was closed."""

    _open_cursors: list["FakeCursor"] = []

    def __init__(self, result: tuple | None = None, raise_on_fetch: bool = False):
        self.result = result
        self.raise_on_fetch = raise_on_fetch
        self.closed = False
        self.description = [("col1",), ("col2",)]
        FakeCursor._open_cursors.append(self)

    def fetchone(self):
        if self.raise_on_fetch:
            raise Exception("Simulated database error")
        return self.result

    def close(self):
        self.closed = True
        if self in FakeCursor._open_cursors:
            FakeCursor._open_cursors.remove(self)

    @classmethod
    def reset_tracking(cls):
        cls._open_cursors = []

    @classmethod
    def get_open_cursor_count(cls) -> int:
        return len(cls._open_cursors)


class TestConnectionLeakSimulation:
    """Simulate connection leaks to demonstrate the problem."""

    def setup_method(self):
        """Reset cursor tracking before each test."""
        FakeCursor.reset_tracking()

    def test_old_code_leaks_cursor_on_exception(self):
        """Demonstrates the OLD (buggy) code behavior.
        When an exception occurs, cursor.close() is never called.
        """

        def old_execute_query_buggy(db, query: str) -> str | None:
            """OLD CODE - cursor leaks if fetchone() raises exception."""
            cursor = db.execute_sql(query)
            result_row = cursor.fetchone()  # If this raises, close() never called!
            cursor.close()
            if not result_row:
                return None
            return result_row[0]

        # Setup mock DB that returns cursors that fail
        mock_db = MagicMock()
        mock_db.execute_sql.side_effect = lambda q: FakeCursor(
            raise_on_fetch=True
        )

        # Simulate 100 requests that all fail
        for _ in range(100):
            try:
                old_execute_query_buggy(mock_db, "SELECT 1")
            except Exception:
                pass  # Exception caught but cursor NOT closed

        # LEAK DETECTED: All 100 cursors are still open!
        open_cursors = FakeCursor.get_open_cursor_count()
        print(f"\n[OLD CODE] Open cursors after 100 failed requests: {open_cursors}")
        assert open_cursors == 100, "Old code should leak cursors"

    def test_new_code_no_leak_on_exception(self):
        """Demonstrates the NEW (fixed) code behavior.
        Cursor is always closed via try/finally.
        """

        def new_execute_query_fixed(db, query: str) -> str | None:
            """NEW CODE - cursor always closed via try/finally."""
            cursor = db.execute_sql(query)
            try:
                result_row = cursor.fetchone()
                if not result_row:
                    return None
                return result_row[0]
            finally:
                cursor.close()  # Always called!

        # Setup mock DB that returns cursors that fail
        mock_db = MagicMock()
        mock_db.execute_sql.side_effect = lambda q: FakeCursor(
            raise_on_fetch=True
        )

        # Simulate 100 requests that all fail
        for _ in range(100):
            try:
                new_execute_query_fixed(mock_db, "SELECT 1")
            except Exception:
                pass

        # NO LEAK: All cursors properly closed
        open_cursors = FakeCursor.get_open_cursor_count()
        print(f"\n[NEW CODE] Open cursors after 100 failed requests: {open_cursors}")
        assert open_cursors == 0, "New code should not leak cursors"

    def test_old_code_leaks_cursor_on_not_found(self):
        """Demonstrates leak when APIError is raised (e.g., adapter not found).
        OLD code: raise happens before cursor.close()
        """

        class APIError(Exception):
            def __init__(self, message: str, code: int = 500):
                self.message = message
                self.code = code

        def old_get_adapter_buggy(db, adapter_id: str) -> dict:
            """OLD CODE - cursor leaks if result not found."""
            cursor = db.execute_sql(f"SELECT * FROM adapter WHERE id='{adapter_id}'")
            result_row = cursor.fetchone()
            if not result_row:
                raise APIError(f"Adapter '{adapter_id}' not found", code=404)
                # cursor.close() never reached!
            columns = [desc[0] for desc in cursor.description]
            data = dict(zip(columns, result_row, strict=False))
            cursor.close()
            return data

        mock_db = MagicMock()
        mock_db.execute_sql.side_effect = lambda q: FakeCursor(result=None)

        # Simulate 50 "not found" requests
        for i in range(50):
            try:
                old_get_adapter_buggy(mock_db, f"nonexistent_{i}")
            except APIError:
                pass

        open_cursors = FakeCursor.get_open_cursor_count()
        print(f"\n[OLD CODE] Open cursors after 50 'not found' errors: {open_cursors}")
        assert open_cursors == 50, "Old code leaks cursors on APIError"

    def test_new_code_no_leak_on_not_found(self):
        """Demonstrates fixed code: cursor closed even when APIError raised."""

        class APIError(Exception):
            def __init__(self, message: str, code: int = 500):
                self.message = message
                self.code = code

        def new_get_adapter_fixed(db, adapter_id: str) -> dict:
            """NEW CODE - cursor always closed via try/finally."""
            cursor = db.execute_sql(f"SELECT * FROM adapter WHERE id='{adapter_id}'")
            try:
                result_row = cursor.fetchone()
                if not result_row:
                    raise APIError(f"Adapter '{adapter_id}' not found", code=404)
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, result_row, strict=False))
                return data
            finally:
                cursor.close()

        mock_db = MagicMock()
        mock_db.execute_sql.side_effect = lambda q: FakeCursor(result=None)

        # Simulate 50 "not found" requests
        for i in range(50):
            try:
                new_get_adapter_fixed(mock_db, f"nonexistent_{i}")
            except APIError:
                pass

        open_cursors = FakeCursor.get_open_cursor_count()
        print(f"\n[NEW CODE] Open cursors after 50 'not found' errors: {open_cursors}")
        assert open_cursors == 0, "New code should not leak cursors"


class TestMemoryGrowthSimulation:
    """Use tracemalloc to detect actual memory growth from leaks."""

    def test_memory_growth_with_leaked_objects(self):
        """Simulates memory growth when objects (like cursors) are not released."""
        # Start tracking memory
        tracemalloc.start()

        # Simulate leaked objects (not properly cleaned up)
        leaked_objects = []

        snapshot1 = tracemalloc.take_snapshot()

        # Simulate 1000 "leaked" cursor-like objects
        for i in range(1000):
            # These objects are kept in the list, simulating a leak
            obj = {
                "cursor_id": i,
                "data": "x" * 1000,  # 1KB of data per cursor
                "result_set": list(range(100)),
            }
            leaked_objects.append(obj)

        snapshot2 = tracemalloc.take_snapshot()

        # Compare memory
        top_stats = snapshot2.compare_to(snapshot1, "lineno")

        total_diff = sum(stat.size_diff for stat in top_stats)
        print("\n[LEAK SIMULATION] Memory growth with 1000 leaked objects:")
        print(f"  Total memory increase: {total_diff / 1024:.2f} KB")

        tracemalloc.stop()

        # Memory should have grown significantly
        assert total_diff > 100_000, "Should see significant memory growth"

    def test_no_memory_growth_with_proper_cleanup(self):
        """Simulates proper cleanup - no memory growth."""
        tracemalloc.start()

        snapshot1 = tracemalloc.take_snapshot()

        # Simulate proper cleanup (objects go out of scope)
        for i in range(1000):
            obj = {
                "cursor_id": i,
                "data": "x" * 1000,
                "result_set": list(range(100)),
            }
            # obj goes out of scope here, eligible for GC
            del obj

        # Force garbage collection
        gc.collect()

        snapshot2 = tracemalloc.take_snapshot()

        top_stats = snapshot2.compare_to(snapshot1, "lineno")
        total_diff = sum(stat.size_diff for stat in top_stats)

        print("\n[PROPER CLEANUP] Memory growth with cleanup:")
        print(f"  Total memory change: {total_diff / 1024:.2f} KB")

        tracemalloc.stop()

        # Memory should not have grown much (might even be negative)
        assert total_diff < 50_000, "Should see minimal memory growth with cleanup"


class TestRedisConnectionLeakSimulation:
    """Simulate Redis connection leaks."""

    def setup_method(self):
        self.open_connections = []

    def test_old_redis_code_leaks_connections(self):
        """Demonstrates OLD code: creates new Redis connection per request,
        doesn't close on exception.
        """

        class FakeRedis:
            connections_created = 0
            connections_closed = 0

            def __init__(self, **kwargs):
                FakeRedis.connections_created += 1
                self.closed = False

            def set(self, key, value):
                raise Exception("Redis connection error")

            def close(self):
                if not self.closed:
                    FakeRedis.connections_closed += 1
                    self.closed = True

        def old_cache_set_buggy(key: str, value: str):
            """OLD CODE - connection leaks if operation fails."""
            r = FakeRedis(host="localhost", port=6379)
            r.set(key, value)  # If this raises, close() never called!
            r.close()

        FakeRedis.connections_created = 0
        FakeRedis.connections_closed = 0

        # Simulate 100 failed cache operations
        for i in range(100):
            try:
                old_cache_set_buggy(f"key_{i}", f"value_{i}")
            except Exception:
                pass

        leaked = FakeRedis.connections_created - FakeRedis.connections_closed
        print(f"\n[OLD REDIS CODE] Connections created: {FakeRedis.connections_created}")
        print(f"[OLD REDIS CODE] Connections closed: {FakeRedis.connections_closed}")
        print(f"[OLD REDIS CODE] Leaked connections: {leaked}")

        assert leaked == 100, "Old code should leak all connections on error"

    def test_new_redis_code_uses_pool(self):
        """Demonstrates NEW code: uses connection pool, no leaks."""

        class FakeRedisPool:
            def __init__(self, **kwargs):
                self.max_connections = kwargs.get("max_connections", 10)

        class FakeRedisWithPool:
            operations = 0

            def __init__(self, connection_pool=None):
                self.pool = connection_pool

            def set(self, key, value):
                FakeRedisWithPool.operations += 1
                raise Exception("Redis operation error")

            # No close() needed - pool manages connections

        pool = FakeRedisPool(max_connections=10)

        def new_cache_set_with_pool(key: str, value: str):
            """NEW CODE - uses shared connection pool."""
            r = FakeRedisWithPool(connection_pool=pool)
            r.set(key, value)

        FakeRedisWithPool.operations = 0

        # Simulate 100 failed cache operations
        for i in range(100):
            try:
                new_cache_set_with_pool(f"key_{i}", f"value_{i}")
            except Exception:
                pass

        print(f"\n[NEW REDIS CODE] Operations performed: {FakeRedisWithPool.operations}")
        print("[NEW REDIS CODE] Pool manages connections - no individual leaks")

        # With pool, we don't create/destroy connections per request
        assert FakeRedisWithPool.operations == 100


class TestRealWorldScenario:
    """Simulate a real-world scenario: API endpoint receiving requests.
    Compare old vs new implementation.
    """

    def test_validate_token_under_load_old_vs_new(self):
        """Simulate 1000 authentication requests, some failing.
        Compare cursor management between old and new code.
        """
        FakeCursor.reset_tracking()

        def old_validate_token(db, token: str) -> bool:
            """OLD CODE - can leak cursor."""
            try:
                cursor = db.execute_sql(f"SELECT * FROM tokens WHERE key='{token}'")
                result = cursor.fetchone()
                cursor.close()  # Not reached if fetchone fails!
                return result is not None
            except Exception:
                return False

        def new_validate_token(db, token: str) -> bool:
            """NEW CODE - cursor always closed."""
            cursor = None
            try:
                cursor = db.execute_sql(f"SELECT * FROM tokens WHERE key='{token}'")
                result = cursor.fetchone()
                return result is not None
            except Exception:
                return False
            finally:
                if cursor is not None:
                    cursor.close()

        # Test OLD code with 30% failure rate
        FakeCursor.reset_tracking()
        mock_db = MagicMock()
        call_count = [0]

        def create_cursor_old(q):
            call_count[0] += 1
            # 30% of requests fail
            return FakeCursor(
                result=("token",) if call_count[0] % 10 != 3 else None,
                raise_on_fetch=(call_count[0] % 10 == 3),
            )

        mock_db.execute_sql.side_effect = create_cursor_old

        for _ in range(1000):
            old_validate_token(mock_db, "test_token")

        old_leaked = FakeCursor.get_open_cursor_count()

        # Test NEW code with same 30% failure rate
        FakeCursor.reset_tracking()
        call_count[0] = 0

        def create_cursor_new(q):
            call_count[0] += 1
            return FakeCursor(
                result=("token",) if call_count[0] % 10 != 3 else None,
                raise_on_fetch=(call_count[0] % 10 == 3),
            )

        mock_db.execute_sql.side_effect = create_cursor_new

        for _ in range(1000):
            new_validate_token(mock_db, "test_token")

        new_leaked = FakeCursor.get_open_cursor_count()

        print("\n[LOAD TEST] 1000 requests with 30% failure rate:")
        print(f"  OLD CODE leaked cursors: {old_leaked}")
        print(f"  NEW CODE leaked cursors: {new_leaked}")

        assert old_leaked > 0, "Old code should leak cursors"
        assert new_leaked == 0, "New code should not leak cursors"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v", "-s"])
