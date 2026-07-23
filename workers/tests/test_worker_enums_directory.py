"""WorkerType.to_directory() — the single source for the on-disk dir mapping (UN-3798).

worker.py's file-path task loader reads to_directory() directly instead of slicing
to_import_path(); these pin the hyphen/underscore mapping and that to_import_path
is built on top of it, so the two can't drift.
"""

from celery import Celery
from shared.enums.worker_enums_base import WorkerType

# The workers autouse conftest fixture finalizes celery's default_app around every
# test; this pure-enum test builds no Celery app of its own, so establish one.
Celery("test-worker-enums").set_default()


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
