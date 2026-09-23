"""WorkerType.to_directory() — the single source for the on-disk dir mapping (UN-3798).

worker.py's file-path task loader reads to_directory() directly instead of slicing
to_import_path(); these pin the hyphen/underscore mapping and that to_import_path is
built on top of it, so the two can't drift.

No Celery app is set up here on purpose: this is a pure-enum module, and the autouse
``_restore_current_celery_app`` fixture now tolerates a missing default app. An
earlier version called ``Celery(...).set_default()`` at import time to satisfy that
fixture, which mutated process-global Celery state for every later test in the
session depending on collection order.
"""

from pathlib import Path

import pytest
from shared.enums.worker_enums_base import WorkerType

_WORKERS_ROOT = Path(__file__).resolve().parents[1]


def test_to_directory_maps_underscored_value_to_hyphenated_dir():
    # The one worker whose on-disk dir differs from its enum value.
    assert WorkerType.API_DEPLOYMENT.value == "api_deployment"
    assert WorkerType.API_DEPLOYMENT.to_directory() == "api-deployment"


def test_to_directory_passthrough_when_dir_equals_value():
    assert WorkerType.GENERAL.to_directory() == "general"


def test_to_import_path_is_built_on_to_directory():
    # to_import_path must derive from to_directory (not a separate mapping), so the
    # directory naming lives in exactly one place.
    wt = WorkerType.API_DEPLOYMENT
    assert wt.to_import_path() == f"{wt.to_directory()}.tasks"


@pytest.mark.parametrize("wt", [w for w in WorkerType if not w.is_pluggable()])
def test_every_worker_type_maps_to_an_existing_directory_with_tasks(wt):
    # The failure mode UN-3798 exists for is enum-vs-disk DRIFT, and worker.py now
    # RAISES on a missing directory (it previously logged and continued) — so drift
    # is a container crash-loop across every replica, not a degraded worker. Pinning
    # two members can't catch that; pin the whole mapping so adding a WorkerType
    # without its directory is a red build instead of a production RuntimeError.
    directory = _WORKERS_ROOT / wt.to_directory()
    assert directory.is_dir(), f"{wt.value} -> {wt.to_directory()} does not exist"
    assert (directory / "tasks.py").is_file(), f"{wt.to_directory()}/tasks.py missing"


@pytest.mark.parametrize("wt", [w for w in WorkerType if w.is_pluggable()])
def test_to_directory_rejects_pluggable_types(wt):
    # Pluggable code lives under pluggable_worker/<value>, so the mapping's
    # passthrough would return a wrong-but-plausible path. Only call ordering kept
    # that unreachable; the precondition is now enforced.
    with pytest.raises(ValueError, match="pluggable"):
        wt.to_directory()
    assert wt.to_import_path() == f"pluggable_worker.{wt.value}.tasks"
