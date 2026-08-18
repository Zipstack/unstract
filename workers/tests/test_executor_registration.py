"""Regression: the executor registry must be populated by importing the task module.

The PG executor consumer (``pg_queue_consumer``) bootstraps a worker by importing
the source worker's ``tasks.py`` — it does NOT import ``executor/worker.py`` (the
Celery entrypoint that historically held ``import executor.executors``). So if the
``@ExecutorRegistry.register`` side-effect import lives only in ``worker.py``, the
PG executor runs ``execute_extraction`` against an EMPTY registry and every
extraction fails with ``No executor registered with name 'legacy'. Available:
(none)``.

This is pinned in a fresh interpreter that imports ONLY ``executor.tasks`` (exactly
what the PG consumer does), so import caching from the rest of the suite can't mask
a regression.
"""

import os
import subprocess
import sys


def test_importing_executor_tasks_registers_executors():
    """Importing executor.tasks alone must register the bundled executors.

    Mirrors the PG-queue consumer's bootstrap (tasks.py, not worker.py). A fresh
    subprocess avoids the suite's other imports pre-populating the registry.
    """
    code = (
        "import executor.tasks\n"
        "from unstract.sdk1.execution.registry import ExecutorRegistry\n"
        "reg = getattr(ExecutorRegistry, '_registry', {})\n"
        "assert 'legacy' in reg, f'registry empty/missing legacy: {sorted(reg)}'\n"
        "print('OK', sorted(reg))\n"
    )
    env = {**os.environ, "WORKER_TYPE": "executor"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, (
        f"executor.tasks import did not register executors.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout
