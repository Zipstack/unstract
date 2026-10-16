"""Every worker's tasks.py must import under BOTH mechanisms worker.py uses.

This exists because a bare ``import dashboard_metrics_tasks`` in scheduler/tasks.py
shipped and crash-looped **worker-general** in integration:

    File "/app/general/tasks.py", line 16, in <module>
        from scheduler.tasks import execute_pipeline_task_v2
    File "/app/scheduler/tasks.py", line 14, in <module>
        import dashboard_metrics_tasks
    ModuleNotFoundError: No module named 'dashboard_metrics_tasks'

The bare form resolves only when ``worker.py`` loads ``scheduler/tasks.py`` BY PATH with
``/app/scheduler`` appended to ``sys.path``. It does not resolve when another worker
imports it as a package module — ``general/tasks.py`` does exactly that, and then
``/app/scheduler`` is not on the path. Flag-off; PG is not involved.

The entire workers suite passed while this was broken, because nothing exercised the two
import mechanisms. That is the gap these close.

**Why subprocesses.** Importing the same file under two names (``dashboard_metrics_tasks``
and ``scheduler.dashboard_metrics_tasks``) creates two module objects and duplicate
Celery task registrations, which breaks other suites that patch one copy — doing this
in-process made test_dashboard_metrics_tasks fail. A fresh interpreter per mechanism is
both properly isolated and a truer reproduction of what a booting worker does.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_WORKERS_ROOT = Path(__file__).resolve().parent.parent

# Discovered, not hardcoded, so a new worker is covered automatically.
_TASK_MODULES = sorted(
    p.parent.name
    for p in _WORKERS_ROOT.glob("*/tasks.py")
    if not p.parent.name.startswith((".", "_")) and p.parent.name != "tests"
)

# Mechanism 2 — `from <worker>.tasks import ...`, the way general/tasks.py reaches
# scheduler/tasks.py. Only the workers root is on sys.path, never the worker's own
# directory: that is the situation that broke.
_PACKAGE_IMPORT_PROBE = """
import importlib, json, sys, traceback
sys.path.insert(0, {root!r})
failures = {{}}
for name in {workers!r}:
    try:
        importlib.import_module(name + ".tasks")
    except Exception:
        failures[name] = traceback.format_exc().strip().splitlines()[-1]
print("RESULT" + json.dumps(failures))
"""

# Mechanism 1 — worker.py's spec_from_file_location load with the worker dir appended,
# i.e. how a worker loads its own tasks.py at boot.
_PATH_IMPORT_PROBE = """
import importlib.util, json, sys, traceback
sys.path.insert(0, {root!r})
failures = {{}}
for name in {workers!r}:
    wd = {root!r} + "/" + name
    sys.path.append(wd)
    try:
        spec = importlib.util.spec_from_file_location("tasks_" + name.replace("-", "_"),
                                                      wd + "/tasks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        failures[name] = traceback.format_exc().strip().splitlines()[-1]
    finally:
        sys.path.remove(wd)
print("RESULT" + json.dumps(failures))
"""


def _run_probe(source: str, workers: list[str] | None = None) -> dict[str, str]:
    proc = subprocess.run(
        [sys.executable, "-c",
         source.format(root=str(_WORKERS_ROOT), workers=workers or _TASK_MODULES)],
        capture_output=True,
        text=True,
        cwd=str(_WORKERS_ROOT),
        timeout=300,
    )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    if not marker:
        pytest.fail(f"probe did not complete.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    return json.loads(marker[-1][len("RESULT") :])


def test_discovery_found_the_workers() -> None:
    """Guard against the glob matching nothing and every case passing vacuously."""
    assert len(_TASK_MODULES) >= 5, _TASK_MODULES
    assert "scheduler" in _TASK_MODULES
    assert "general" in _TASK_MODULES


# A hyphenated directory (api-deployment) can never be imported package-style — it is
# not a valid Python identifier — so only the file-path mechanism applies to it.
_PACKAGE_IMPORTABLE = [w for w in _TASK_MODULES if w.isidentifier()]


def test_every_tasks_module_imports_as_a_package() -> None:
    """The mechanism that broke: worker's own dir NOT on sys.path."""
    failures = _run_probe(_PACKAGE_IMPORT_PROBE, workers=_PACKAGE_IMPORTABLE)
    assert not failures, "package-style import failed:\n" + "\n".join(
        f"  {k}: {v}" for k, v in sorted(failures.items())
    )


def test_every_tasks_module_imports_by_file_path() -> None:
    """The mechanism worker.py uses for a worker's own tasks.py."""
    failures = _run_probe(_PATH_IMPORT_PROBE)
    assert not failures, "file-path import failed:\n" + "\n".join(
        f"  {k}: {v}" for k, v in sorted(failures.items())
    )


def test_scheduler_tasks_registers_every_periodic_under_its_wire_name() -> None:
    """Loading ``scheduler/tasks.py`` must REGISTER the periodic proxies, not
    merely import without error.

    This replaces a test that stated this exact intent -- "asserting only that
    scheduler.tasks imports would still pass if someone 'fixed' it by deleting
    the import" -- and then imported ``scheduler.dashboard_metrics_tasks``
    DIRECTLY, which registers the tasks by itself. So it passed no matter what
    ``scheduler/tasks.py`` contained, and it passed through the very regression
    it was written to catch: in a79e9d69 pre-commit.ci's auto-fix deleted BOTH
    side-effect imports from scheduler/tasks.py (ruff's isort merged the two
    `from scheduler import ...` statements, which relocated each `# noqa` onto a
    member line where it no longer suppresses the statement-level F401, and
    pycln -- `all = true` -- then removed both). Nothing went red.

    The failure mode is silent: the worker boots fine and only the scheduled
    messages are rejected as unknown tasks, so dashboard metrics stop updating
    and Agent-KV jobs stop being swept with no error anywhere near the cause.
    Hence going through ``scheduler.tasks`` -- what a booting worker actually
    loads -- and asserting against the Celery registry rather than the modules.
    """
    source = """
import importlib, json, sys
sys.path.insert(0, {root!r})
importlib.import_module("scheduler.tasks")
from celery import current_app
print("RESULT" + json.dumps(sorted(
    n for n in current_app.tasks
    if n.startswith("dashboard_metrics.") or n.startswith("agent_kv.")
)))
"""
    proc = subprocess.run(
        [sys.executable, "-c", source.format(root=str(_WORKERS_ROOT))],
        capture_output=True,
        text=True,
        cwd=str(_WORKERS_ROOT),
        # Resolved at import with no default; unset, scheduler.tasks raises
        # before any registration and this would fail for the wrong reason.
        env={**os.environ, "INTERNAL_API_BASE_URL": "http://localhost:8000"},
        timeout=300,
    )
    marker = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")]
    assert marker, f"probe failed:\n{proc.stdout}\n{proc.stderr}"
    assert json.loads(marker[-1][len("RESULT") :]) == [
        # Pinned to verbatim Beat/PG-scheduler rows -- the consumer resolves
        # these BY NAME, so a rename here is a silent un-registration too.
        "agent_kv.sweep",
        "agent_kv.ttl_cleanup",
        "dashboard_metrics.aggregate_from_sources",
        "dashboard_metrics.cleanup_daily_data",
        "dashboard_metrics.cleanup_hourly_data",
    ]
