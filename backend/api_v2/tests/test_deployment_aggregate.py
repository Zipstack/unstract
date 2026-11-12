"""``api/deployment/aggregate/`` and the status, owner, last-run and failing
list filters.

The aggregate reads the list's own filtered queryset, so for every filter and
caller its ``total`` must equal the list's ``count``.
"""

import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from platform_api.models import PlatformApiKey
from platform_api.services import create_api_user_for_key
from workflow_manager.workflow_v2.tests.list_rows import (
    AggregateRouteChecks,
    COMPLETED,
    ERROR,
    FIVE_ERRORS,
    PENDING,
    STOPPED,
    ListRowsSeed,
)

from api_v2.api_deployment_views import APIDeploymentViewSet
from api_v2.tests.test_deployment_listing import _MIDDLEWARE

URL = "/deployment/"
CONTRACT = json.loads(
    (
        Path(__file__).parent / "deployment-aggregate-response.schema.json"
    ).read_text()
)


class DeploymentAggregateTests(AggregateRouteChecks, ListRowsSeed, TestCase):
    contract = CONTRACT
    view = APIDeploymentViewSet
    url = URL

    def setUp(self) -> None:
        super().setUp()
        # Last run 9h ago, success.
        self.ok = self._deployment("Invoices")
        self._runs(self.ok, [ERROR, COMPLETED], hours_ago=10)
        self._share(self.ok, self.viewer)
        # Last run 5h ago, five errors in a row.
        self.broken = self._deployment("Receipts", owner=self.coowner)
        self._runs(self.broken, [COMPLETED, *FIVE_ERRORS], hours_ago=10)
        # Last run 19h ago, stopped.
        self.stopped = self._deployment("Contracts")
        self._runs(self.stopped, [COMPLETED, STOPPED], hours_ago=20)
        # Only an orphan run, 30h ago; visible to the whole org.
        self.fresh = self._deployment("Invoices draft", shared_to_org=True)
        self._runs(self.fresh, [PENDING], hours_ago=30)
        self.paused = self._deployment("Paused", is_active=False)
        self._runs(self.paused, FIVE_ERRORS, hours_ago=40)
        # Another organisation's rows are never counted.
        self._runs(self._deployment("Elsewhere", org=self.org_b), FIVE_ERRORS)

    def _names(self, **params: Any) -> set[str]:
        return {row["display_name"] for row in self._list(**params)["results"]}

    def _filter_cases(self) -> list[dict[str, Any]]:
        after = (self.now - timedelta(hours=10)).isoformat()
        before = (self.now - timedelta(hours=8)).isoformat()
        return [
            {},
            {"search": "invoices"},
            {"workflow": str(self.ok.workflow_id)},
            {"api_name": self.broken.api_name},
            {"status": "success"},
            {"status": "error"},
            {"status": "never_run"},
            {"status": "inactive"},
            {"owner": self.coowner.id},
            {"last_run_after": after},
            {"last_run_before": before},
            {"failing": "true"},
            {"search": "invoices", "status": "never_run"},
            {"owner": self.owner.id, "status": "error", "last_run_before": before},
        ]

    def test_totals_equal_the_list_count_for_every_filter_and_caller(self) -> None:
        self.assertEqual(self._mismatches_with_the_list(self._filter_cases()), [])

    def test_the_counts_follow_the_status_rule(self) -> None:
        summary = self._aggregate()

        self.assertEqual(summary["total"], 5)
        self.assertEqual(
            summary["by_status"],
            {
                "success": 1,
                "partial_success": 0,
                "error": 2,
                "never_run": 1,
                "inactive": 1,
            },
        )

    def test_each_caller_counts_only_what_it_can_see(self) -> None:
        self.assertEqual(self._aggregate(self.owner)["total"], 4)
        self.assertEqual(self._aggregate(self.coowner)["total"], 2)
        self.assertEqual(self._aggregate(self.viewer)["total"], 2)
        self.assertEqual(self._aggregate(self.outsider)["total"], 1)

    def test_a_failing_row_names_its_owner_and_streak(self) -> None:
        summary = self._aggregate()

        self.assertEqual(summary["failing_count"], 1)
        (row,) = summary["failing"]
        self.assertEqual(row["id"], str(self.broken.pk))
        self.assertEqual(row["name"], "Receipts")
        self.assertEqual(row["owner_email"], self.coowner.email)
        self.assertEqual(row["failures_in_a_row"], 5)
        self.assertEqual(self._hours_ago(row["last_success"]), 10)
        self.assertEqual(self._hours_ago(row["failing_since"]), 9)
        self.assertEqual(self._hours_ago(row["last_failure"]), 5)

    def test_each_list_filter_selects_its_rows(self) -> None:
        cases = {
            "status=success": ({"status": "success"}, {"Invoices"}),
            "status=error": ({"status": "error"}, {"Receipts", "Contracts"}),
            "status=never_run": ({"status": "never_run"}, {"Invoices draft"}),
            "status=inactive": ({"status": "inactive"}, {"Paused"}),
            "owner": ({"owner": self.coowner.id}, {"Receipts"}),
            "failing": ({"failing": "true"}, {"Receipts"}),
            "last_run_after": (
                {"last_run_after": (self.now - timedelta(hours=9)).isoformat()},
                {"Invoices", "Receipts"},
            ),
            "last_run_before": (
                {"last_run_before": (self.now - timedelta(hours=19)).isoformat()},
                {"Contracts", "Invoices draft", "Paused"},
            ),
        }
        for label, (params, expected) in cases.items():
            with self.subTest(label):
                self.assertEqual(self._names(**params), expected)

    def test_list_filters_combine_with_each_other_and_the_old_ones(self) -> None:
        self.assertEqual(
            self._names(status="error", owner=self.owner.id), {"Contracts"}
        )
        self.assertEqual(self._names(search="invoices", status="success"), {"Invoices"})
        self.assertEqual(self._names(failing="false"), self._names())

    def test_the_filter_step_changes_nothing_without_its_parameters(self) -> None:
        """Same body and SQL as with the viewset's filter step removed."""
        with_the_step, without_it = self._list_with_and_without_the_filter_step(
            search="invoices"
        )

        self.assertEqual(with_the_step, without_it)
        self.assertEqual(self._list(status="")["count"], self._list()["count"])

    def test_a_malformed_parameter_is_a_bad_request(self) -> None:
        for params in (
            {"workflow": "not-a-uuid"},
            {"status": "stopped"},
            {"owner": "abc"},
            {"last_run_after": "yesterday"},
            {"failing": "maybe"},
        ):
            for action in ("list", "aggregate"):
                with self.subTest(action=action, **params):
                    response = self._call(
                        APIDeploymentViewSet, action, self.admin, URL, **params
                    )
                    self.assertEqual(response.status_code, 400)

    def test_the_query_count_does_not_grow_with_the_rows(self) -> None:
        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                self._aggregate()
            return len(captured)

        queries()  # Warm the per-process caches both runs read.
        few = queries()
        for n in range(9):
            row = self._deployment(f"More {n}", owner=self.coowner)
            self._runs(row, FIVE_ERRORS if n % 2 else [COMPLETED])

        self.assertEqual(queries(), few)


@override_settings(MIDDLEWARE=_MIDDLEWARE)
class DeploymentAggregateRouteTests(ListRowsSeed, TestCase):
    def test_the_route_is_not_taken_for_a_deployment_id(self) -> None:
        match = resolve(reverse("tenant:api_deployment_aggregate"))

        self.assertIs(match.func.cls, APIDeploymentViewSet)
        self.assertEqual(match.func.actions["get"], "aggregate")

    def test_a_platform_key_reads_the_aggregate(self) -> None:
        """Reached the same way as the list it counts."""
        self._deployment("Invoices")
        key = PlatformApiKey.objects.create(
            name=f"key-{secrets.token_hex(4)}", description="test", organization=self.org
        )
        create_api_user_for_key(key, self.org)
        org_path = f"/{settings.PATH_PREFIX}/unstract/{self.org.organization_id}"

        response = self.client.get(
            f"{org_path}/api/deployment/aggregate/",
            HTTP_AUTHORIZATION=f"Bearer {key.key}",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], 1)
