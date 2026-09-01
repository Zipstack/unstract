"""Guard: the tier a schedule row declares reaches the task (UN-3974, AC-1).

Two schedulers fire the same task name at two different implementations. Beat reads
``PeriodicTask.kwargs`` and calls the Django ``@shared_task`` directly; the PG scheduler
reads ``PgPeriodicTask.task_kwargs`` and goes through the worker proxy and the internal
endpoint to the same function. Both legs have to carry ``tier``, and a break in either is
invisible — the job still runs, still returns success, and just writes the wrong tiers.

The worker half of the PG leg is pinned in ``workers/tests/test_dashboard_metrics_tasks.py``;
this covers the endpoint that receives it and the Beat leg's kwargs.

DB-free: the task is mocked, and the Beat kwargs are read from the migration spec rather
than from a migrated database.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
from typing import Any
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from rest_framework.test import APIRequestFactory  # noqa: E402

from dashboard_metrics import internal_views  # noqa: E402
from dashboard_metrics.tasks import (  # noqa: E402
    AggregationTier,
    aggregate_metrics_from_sources,
)

_SPLIT_MIGRATION = "dashboard_metrics.migrations.0006_split_aggregation_schedule"
_ENDPOINT = "/internal/v1/dashboard-metrics/aggregate/"


def _post(body: dict[str, Any]) -> tuple[int, Any]:
    """POST to the aggregate endpoint with the task mocked; return status and its kwargs."""
    view = internal_views.AggregateMetricsAPIView.as_view()
    request = APIRequestFactory().post(_ENDPOINT, body, format="json")
    with mock.patch.object(
        internal_views, "aggregate_metrics_from_sources", return_value={"ok": True}
    ) as task:
        response = view(request)
    return response.status_code, (task.call_args.kwargs if task.call_args else None)


class TestThePgLegCarriesTheTier:
    """The endpoint the worker proxy POSTs to."""

    @pytest.mark.parametrize("tier", ["hourly", "daily_monthly", "all"])
    def test_the_endpoint_forwards_the_tier_to_the_task(self, tier: str) -> None:
        status, called_with = _post({"tier": tier})
        assert status == 200
        assert called_with == {"tier": tier}

    def test_an_omitted_tier_leaves_the_task_default_in_place(self) -> None:
        """Not 'hourly', and not nothing: the task's own default is `all`, and passing
        anything here would override it during the pre-0005 deploy window.
        """
        status, called_with = _post({})
        assert status == 200
        assert called_with == {}

    def test_an_unrecognised_tier_is_rejected_rather_than_ignored(self) -> None:
        """A silent no-op would look like a successful run that wrote nothing.

        Runs against the real task, not the mock: the 400 comes from the ValueError the
        task raises, and a mock would accept anything and return 200. The tier is
        validated on the task's first line, so nothing touches the database.
        """
        view = internal_views.AggregateMetricsAPIView.as_view()
        response = view(APIRequestFactory().post(_ENDPOINT, {"tier": "houry"}, format="json"))
        assert response.status_code == 400
        assert "houry" in str(response.data)


class TestTheBeatLegCarriesTheTier:
    """Beat passes the row's stored JSON kwargs straight into the task signature."""

    @pytest.fixture(scope="class")
    def declared_kwargs(self) -> dict[str, dict[str, Any]]:
        mod = importlib.import_module(_SPLIT_MIGRATION)
        return {s["name"]: {"tier": s["tier"]} for s in mod.AGGREGATION_SCHEDULES}

    def test_both_rows_declare_a_tier(
        self, declared_kwargs: dict[str, dict[str, Any]]
    ) -> None:
        assert len(declared_kwargs) == 2
        assert all("tier" in kw for kw in declared_kwargs.values())

    def test_every_declared_kwarg_set_binds_to_the_task_signature(
        self, declared_kwargs: dict[str, dict[str, Any]]
    ) -> None:
        """A row declaring a kwarg the task does not accept fails at call time, inside
        the worker, where it surfaces as a retrying task rather than a bad schedule.
        """
        signature = inspect.signature(aggregate_metrics_from_sources)
        for kwargs in declared_kwargs.values():
            signature.bind(**kwargs)

    def test_every_declared_tier_is_a_real_tier(
        self, declared_kwargs: dict[str, dict[str, Any]]
    ) -> None:
        """The migration cannot import the enum, so it repeats the literals. A typo
        there raises inside the task on every single run."""
        for kwargs in declared_kwargs.values():
            AggregationTier(kwargs["tier"])

    def test_beat_stores_the_kwargs_as_json_the_task_can_receive(self) -> None:
        """Beat's kwargs column is a JSON *string*; PgPeriodicTask's is a JSONField.
        The Beat side has to round-trip back to the same mapping."""
        mod = importlib.import_module(_SPLIT_MIGRATION)
        for spec in mod.AGGREGATION_SCHEDULES:
            assert json.loads(json.dumps({"tier": spec["tier"]})) == {"tier": spec["tier"]}
