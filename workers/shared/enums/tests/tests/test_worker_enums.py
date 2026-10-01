"""The cloud WorkerType overlay must bind every method ``worker.py`` calls.

Regression guard for the ``'workertype' object has no attribute 'to_directory'``
crash: cloud's ``worker_enums.py`` rebuilds ``WorkerType`` from scratch via the
functional ``Enum(...)`` API, so it does NOT inherit the OSS base's methods and must
re-bind each one. ``worker.py``'s file-path task loader (OSS #2197 / UN-3798) calls
``to_directory()`` directly for non-pluggable workers; a missing bind crashes the
worker at Celery app-load. The OSS base is faked here so the test is env-independent
(no ``copy_cloud_deps`` / OSS checkout needed).
"""

import importlib.util
import sys
import types

import pytest
from enum import Enum
from pathlib import Path

_ENUMS_PY = Path(__file__).resolve().parent.parent / "worker_enums.py"


def _load_overlay():
    """Load cloud worker_enums.py by file path over a faked OSS base."""
    base = types.ModuleType("shared.enums.worker_enums_base")
    base.WorkerType = Enum(
        "WorkerType",
        {"API_DEPLOYMENT": "api_deployment", "GENERAL": "general"},
        type=str,
    )
    base.QueueName = Enum("QueueName", {"CELERY": "celery"}, type=str)
    base.WorkerStatus = Enum("WorkerStatus", {"ACTIVE": "active"}, type=str)
    for name in ("shared", "shared.enums"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["shared.enums.worker_enums_base"] = base
    spec = importlib.util.spec_from_file_location(
        "shared.enums.worker_enums", _ENUMS_PY
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_to_directory_is_bound_and_maps_hyphenated_dir():
    # The exact call worker.py makes for non-pluggable workers (the one that crashed).
    wt = _load_overlay().WorkerType
    assert wt.API_DEPLOYMENT.to_directory() == "api-deployment"
    assert wt.GENERAL.to_directory() == "general"


def test_to_import_path_builds_on_to_directory():
    wt = _load_overlay().WorkerType
    assert wt.API_DEPLOYMENT.to_import_path() == "api-deployment.tasks"
    assert wt.GENERAL.to_import_path() == "general.tasks"


@pytest.mark.parametrize(
    "member,port",
    [
        ("BULK_DOWNLOAD", 8096),
        ("AGENTIC_CALLBACK", 8097),
        # AGENTIC_STUDIO is added by this epic and was the one member never asserted.
        # Omit it from pluggable_names and to_import_path() returns
        # "agentic_studio.tasks" instead of "pluggable_worker.agentic_studio.tasks",
        # crashing the worker at Celery app-load — the identical class of bug this
        # module exists to guard. The helm suite can't catch it (it only renders
        # manifests).
        ("AGENTIC_STUDIO", 8098),
        # UN-3844 — same guard for the subscription worker: omit it from
        # pluggable_names and to_import_path() returns "subscription.tasks"
        # instead of "pluggable_worker.subscription.tasks", crashing the worker
        # at Celery app-load.
        ("SUBSCRIPTION", 8099),
    ],
)
def test_pluggable_workers_use_pluggable_worker_path(member, port):
    wt = getattr(_load_overlay().WorkerType, member)
    assert wt.is_pluggable() is True
    assert wt.to_import_path() == f"pluggable_worker.{wt.value}.tasks"
    assert wt.to_health_port() == port
