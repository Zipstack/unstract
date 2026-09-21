"""Regression: the file_processing worker must not boot the executor stack.

``structure_tool_task`` dispatches all real extraction work to the executor
worker over the PG queue. From the ``executor`` package it needs only two cheap
things: ``ExecutorToolShim`` (a StreamMixin wrapper) and some string constants.

Both used to drag in ``LegacyExecutor`` and every adapter behind it, because
``executor/__init__.py`` eagerly imported ``.worker``, which imported
``executor.executors``, which imported ``LegacyExecutor`` and ran entry-point
discovery. ``structure_tool_task`` makes those imports inside the task function,
so the cost landed on each forked child's FIRST task rather than at startup —
~9s per child, measured on staging (UN-4136).

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

# The expensive modules: ``legacy_executor`` pulls the x2text adapter stack at
# module scope, and ``executor.worker`` builds the Celery app.
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


def test_loading_executor_tasks_suppresses_celery_result_logging():
    """The trace logger must be muted by the module the executor actually loads.

    ``celery.app.trace`` logs the full result dict on task success, which for
    ``execute_extraction`` is extracted customer document text. The
    ``setLevel(WARNING)`` that mutes it used to live in ``executor/worker.py``
    and was reached only because ``executor/__init__.py`` eagerly imported
    ``.worker`` — so making that import lazy silently un-suppressed it, and
    every extraction would have logged ~1KB of the payload at INFO.

    Nothing else in the repo sets this level, and no launcher runs
    ``celery -A executor``, so ``executor/tasks.py`` — which ``workers/worker.py``
    exec-loads by path for both executor roles — is the only module that can
    carry it. A fresh interpreter is required: another test importing
    ``executor.worker`` first would mask the regression.
    """
    code = "\n".join(
        [
            "import logging, sys",
            "import executor.tasks",  # exactly what the deployed executor loads
            "lvl = logging.getLogger('celery.app.trace').level",
            "assert lvl == logging.WARNING, f'trace logger not suppressed: {lvl}'",
            # The suppression must not come back via the expensive import.
            "assert 'executor.worker' not in sys.modules, 'pulled in executor.worker'",
            "print('OK')",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, "WORKER_TYPE": "executor"},
        cwd=_WORKERS_DIR,
    )
    assert result.returncode == 0, (
        "executor.tasks did not suppress celery.app.trace result logging.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
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
