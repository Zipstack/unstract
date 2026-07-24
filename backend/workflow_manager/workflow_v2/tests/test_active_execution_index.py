"""Guard: the active-execution partial index predicate stays in sync with the
canonical terminal-status set.

``we_active_by_workflow_idx`` (``WorkflowExecution.Meta.indexes``) excludes
terminal statuses via a hardcoded ``~Q(status__in=[...])`` literal — mirrored a
third time in migration 0023's ``RunSQL``. This asserts that literal equals
``ExecutionStatus.terminal_values()`` so it cannot silently drift from the enum
(e.g. when a new terminal status is added). Model introspection only — no test
database required.
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from unstract.core.data_models import ExecutionStatus  # noqa: E402

INDEX_NAME = "we_active_by_workflow_idx"


def _excluded_statuses(condition) -> set[str]:
    """Pull the status set out of the index's ``~Q(status__in=[...])`` condition."""
    for child in condition.children:
        if isinstance(child, tuple) and child[0] == "status__in":
            return set(child[1])
    raise AssertionError("index condition has no status__in clause")


def _active_index():
    model = apps.get_model("workflow_v2", "WorkflowExecution")
    return next((i for i in model._meta.indexes if i.name == INDEX_NAME), None)


def test_active_index_exists_and_is_a_negated_partial():
    index = _active_index()
    assert index is not None, f"{INDEX_NAME} missing from Meta.indexes"
    assert index.fields == ["workflow_id"]
    assert index.condition is not None and index.condition.negated, (
        "index must EXCLUDE (NOT IN) terminal statuses"
    )


def test_active_index_excludes_exactly_the_terminal_statuses():
    # Drift guard: the hardcoded predicate must equal the canonical terminal set,
    # so adding a terminal status to the enum without updating the index fails here.
    index = _active_index()
    assert index is not None
    assert _excluded_statuses(index.condition) == set(ExecutionStatus.terminal_values())
