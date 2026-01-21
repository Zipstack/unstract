# Platform Service Tests

This directory contains tests for the platform-service, including memory leak simulation tests.

## Prerequisites

```bash
cd platform-service
uv sync --group test
```

## Running Tests

### Run All Tests

```bash
uv run pytest tests/ -v
```

### Run Memory Leak Simulation Tests

```bash
# With verbose output showing leak counts
uv run pytest tests/test_memory_leak_simulation.py -v -s
```

### Run Specific Test Class

```bash
# Test cursor leak simulation
uv run pytest tests/test_memory_leak_simulation.py::TestConnectionLeakSimulation -v -s

# Test memory growth simulation
uv run pytest tests/test_memory_leak_simulation.py::TestMemoryGrowthSimulation -v -s

# Test Redis connection leak simulation
uv run pytest tests/test_memory_leak_simulation.py::TestRedisConnectionLeakSimulation -v -s

# Test real-world load scenario
uv run pytest tests/test_memory_leak_simulation.py::TestRealWorldScenario -v -s
```

## Test Files

### `test_memory_leak_simulation.py`

Demonstrates and verifies resource leak fixes by comparing OLD (leaky) vs NEW (fixed) code patterns.

| Test Class | Purpose |
|------------|---------|
| `TestConnectionLeakSimulation` | Shows cursor leaks when exceptions occur before `close()` |
| `TestMemoryGrowthSimulation` | Uses `tracemalloc` to measure actual memory growth |
| `TestRedisConnectionLeakSimulation` | Demonstrates Redis connection leaks vs pool usage |
| `TestRealWorldScenario` | Simulates 1000 requests with 30% failure rate |

**Sample Output:**
```text
[OLD CODE] Open cursors after 100 failed requests: 100  ❌ LEAKED
[NEW CODE] Open cursors after 100 failed requests: 0    ✅ NO LEAK

[LEAK SIMULATION] Memory growth with 1000 leaked objects: 1033.37 KB
[PROPER CLEANUP] Memory growth with cleanup: 0.66 KB

[LOAD TEST] 1000 requests with 30% failure rate:
  OLD CODE leaked cursors: 100
  NEW CODE leaked cursors: 0
```

### `test_auth_middleware.py`

Basic authentication middleware tests.

## Writing New Tests

When adding tests for resource management, use these patterns:

### Testing Cursor Cleanup

```python
from unittest.mock import MagicMock

def test_cursor_closed_on_exception(self):
    mock_cursor = MagicMock()
    mock_cursor.fetchone.side_effect = Exception("DB error")
    mock_db = MagicMock()
    mock_db.execute_sql.return_value = mock_cursor

    with pytest.raises(Exception):
        your_function(mock_db)

    # Verify cursor was closed despite exception
    mock_cursor.close.assert_called_once()
```

### Testing Memory with tracemalloc

```python
import tracemalloc

def test_no_memory_leak(self):
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # Run your code here

    snapshot2 = tracemalloc.take_snapshot()
    stats = snapshot2.compare_to(snapshot1, "lineno")
    total_diff = sum(s.size_diff for s in stats)

    tracemalloc.stop()
    assert total_diff < threshold, "Memory leak detected"
```
