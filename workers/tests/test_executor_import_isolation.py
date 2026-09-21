"""Regression: the file_processing worker must not boot the executor stack.

``structure_tool_task`` dispatches all real extraction work to the executor
worker over the PG queue. From the ``executor`` package it needs only two cheap
things: ``ExecutorToolShim`` (a StreamMixin wrapper) and some string constants.

Both used to drag in ``LegacyExecutor`` and every adapter behind it, because
``executor/__init__.py`` eagerly imported ``.worker``, which imported
``executor.executors``, which imported ``LegacyExecutor`` and ran entry-point
discovery. The imports are function-local, so the cost was deferred to each
forked child's FIRST task — ~9s measured per child in
``unstract-worker-pg-api-file-processing`` on staging, times the supervisor's
20 prefork children, landing during serving.

These pin the import graph, not a duration: a timing assertion would be flaky on
CI, while the thing that actually regresses is an eager import creeping back
into either ``__init__``. Each runs in a fresh interpreter so the rest of the
suite cannot pre-import the stack and mask the regression.
"""

import os
import subprocess
import sys

# Importing these must not pull the executor stack in behind them.
_FILE_PROCESSING_IMPORTS = (
    "from executor.executor_tool_shim import ExecutorToolShim",
    "from executor.executors.constants import PromptServiceConstants",
)

# Cheap to import on their own; each is the head of the expensive chain.
_MUST_NOT_LOAD = (
    "executor.worker",
    "executor.executors.legacy_executor",
)

_WORKERS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(snippet: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKER_TYPE": "file_processing"},
        cwd=_WORKERS_DIR,
    )


def test_file_processing_imports_do_not_load_the_executor_stack():
    """Neither import may leave the executor worker or LegacyExecutor loaded."""
    code = "\n".join(
        [
            "import sys",
            *_FILE_PROCESSING_IMPORTS,
            f"loaded = [m for m in {_MUST_NOT_LOAD!r} if m in sys.modules]",
            "assert not loaded, f'eagerly imported: {loaded}'",
            "print('OK')",
        ]
    )
    result = _run(code)
    assert result.returncode == 0, (
        "importing ExecutorToolShim / PromptServiceConstants pulled in the "
        f"executor stack.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_importing_the_executor_package_does_not_build_the_celery_app():
    """``import executor`` alone must stay cheap.

    ``celery_app`` is still reachable — it resolves on attribute access (PEP
    562) — so this pins laziness, not removal.
    """
    code = "\n".join(
        [
            "import sys, executor",
            "assert 'executor.worker' not in sys.modules, 'executor/__init__ built the app'",
            "assert executor.celery_app is not None, 'celery_app no longer resolves'",
            "assert 'executor.worker' in sys.modules, 'attribute access did not load it'",
            "print('OK')",
        ]
    )
    result = _run(code)
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "OK" in result.stdout
