"""Execution-level stage timing aggregate (UN-3451).

The aggregate reads every file row's JSON payload, so it is computed on the
detail view only — doing it per row of the executions LIST would be an N+1
over a table that can hold thousands of rows per execution.

Unit tests: the queryset chain is mocked, so no database is needed.
"""

import os
from unittest.mock import MagicMock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from workflow_manager.execution.serializer.execution import (  # noqa: E402
    ExecutionSerializer,
)

PAYLOADS = [
    {
        "stages": {"queue_wait": 1.0, "tool_execution": 10.0},
        "tool_split": {"extraction": 6.0},
        "total": 11.5,
        "unaccounted": 0.5,
    },
    {
        "stages": {"queue_wait": 2.5, "tool_execution": 4.0},
        "tool_split": {"extraction": 2.0},
        "total": 6.5,
        "unaccounted": 0.0,
    },
]


def _execution(payloads=PAYLOADS):
    """A WorkflowExecution stand-in whose file_executions yield `payloads`."""
    obj = MagicMock()
    obj.id = "exec-1"
    chain = obj.file_executions.filter.return_value.values_list.return_value
    chain.iterator.return_value = iter(payloads)
    return obj


def _serializer(detail, action=None):
    view = MagicMock()
    view.detail = detail
    view.action = action
    serializer = ExecutionSerializer()
    serializer._context = {"view": view}
    return serializer


def _serializer_for_real_route(url_name):
    """Build the serializer against the view this project's URLconf really creates.

    The gate has to hold for how the viewset is actually wired up, not for a
    hand-made context. ``ViewSetMixin.as_view`` sets ``cls.detail = None`` and
    only a router overrides it; these routes are registered by hand, so a
    ``detail``-only check returned None on the live detail route and the card
    never rendered.
    """
    from workflow_manager.execution import urls as execution_urls

    pattern = next(
        p for p in execution_urls.urlpatterns if getattr(p, "name", None) == url_name
    )
    view_func = pattern.callback
    view = view_func.cls(**getattr(view_func, "initkwargs", {}))
    # as_view()'s closure sets these per request; replicate for the GET mapping
    # this route was registered with.
    view.action_map = view_func.actions
    view.action = view_func.actions.get("get")

    serializer = ExecutionSerializer()
    serializer._context = {"view": view}
    return serializer


def test_detail_view_returns_the_aggregate():
    result = _serializer(True).get_aggregated_stage_timings(_execution())

    assert result["files"] == 2
    assert result["stages"]["tool_execution"] == 14.0
    assert result["stages"]["queue_wait"] == 3.5
    assert result["tool_split"]["extraction"] == 8.0
    # The chart divides by `total`, so the rows must add up to it.
    assert result["unaccounted"] == 0.5
    assert sum(result["stages"].values()) + result["unaccounted"] == result["total"]


def test_the_real_detail_route_returns_the_aggregate():
    """Regression: the live route sets detail=None, so `detail` alone fails."""
    serializer = _serializer_for_real_route("execution-detail")

    # The precondition the bug hinged on — assert it so this test keeps
    # testing the thing if DRF's as_view ever starts setting the flag.
    assert serializer.context["view"].detail is None

    result = serializer.get_aggregated_stage_timings(_execution())

    assert result is not None
    assert result["files"] == 2


def test_the_real_list_route_skips_the_scan():
    serializer = _serializer_for_real_route("execution-list")
    obj = _execution()

    assert serializer.get_aggregated_stage_timings(obj) is None
    obj.file_executions.filter.assert_not_called()


def test_list_view_skips_the_scan_entirely():
    obj = _execution()

    assert _serializer(False).get_aggregated_stage_timings(obj) is None
    # The point of the guard is the query that never runs.
    obj.file_executions.filter.assert_not_called()


def test_a_router_supplied_detail_flag_is_honoured():
    """A future @action(detail=True) route needs no action-name allow-list."""
    result = _serializer(True, action="timings").get_aggregated_stage_timings(
        _execution()
    )

    assert result is not None


def test_a_view_that_declares_nothing_is_treated_as_a_list():
    obj = _execution()
    serializer = ExecutionSerializer()
    serializer._context = {}

    assert serializer.get_aggregated_stage_timings(obj) is None
    obj.file_executions.filter.assert_not_called()


def test_no_timed_files_yields_none_rather_than_an_empty_shell():
    result = _serializer(True).get_aggregated_stage_timings(_execution([]))

    assert result is None


def test_a_broken_queryset_does_not_fail_the_response():
    """Timing is diagnostic; the execution detail page must still render."""
    obj = MagicMock()
    obj.id = "exec-1"
    obj.file_executions.filter.side_effect = RuntimeError("db gone")

    assert _serializer(True).get_aggregated_stage_timings(obj) is None


def test_only_rows_with_a_payload_are_scanned():
    obj = _execution()

    _serializer(True).get_aggregated_stage_timings(obj)

    obj.file_executions.filter.assert_called_once_with(stage_timings__isnull=False)
