"""The published contract matches what the endpoint serves.

* Real responses validate against the committed JSON Schema.
* Each OSS type's context line and route params match values copied from
  the README's type table; the table's order, type, label and route key
  columns are checked against the registered providers.
* The endpoint is mounted on the tenant path.
"""

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import jsonschema
from django.db import connection
from django.test import TestCase
from django.urls import resolve
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin, make_user

from global_search.constants import OSSSearchType as T
from global_search.oss_providers import OSS_PROVIDERS, WorkflowProvider
from global_search.providers import SearchProvider
from global_search.tests.base import OSS_BUILDERS, search
from global_search.views import GlobalSearchView

APP_DIR = Path(__file__).parents[1]
SCHEMA = json.loads((APP_DIR / "contract" / "search-response.schema.json").read_text())
README = (APP_DIR / "README.md").read_text()


class SearchContractTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()

    def test_responses_validate_against_schema(self) -> None:
        for type_key, build in OSS_BUILDERS.items():
            item = build(self.org, self.owner, f"theta-{type_key}", "theta notes")
            item.memberships.create(user=self.owner, role="owner")
        response = search(self.admin, q="theta", limit=20)
        jsonschema.validate(response.data, SCHEMA)
        self.assertEqual(
            [g["type"] for g in response.data["groups"]],
            [p.type_key for p in sorted(OSS_PROVIDERS, key=lambda p: p.order)],
        )

    def test_context_and_route_params_per_type(self) -> None:
        items = {}
        for type_key, build in OSS_BUILDERS.items():
            items[type_key] = build(self.org, self.owner, f"theta-{type_key}")
            items[type_key].memberships.create(user=self.owner, role=ResourceRole.OWNER)
        response = search(self.admin, q="theta", limit=20)
        results = {g["type"]: g["results"][0] for g in response.data["groups"]}

        def parent(type_key: str) -> str:
            return items[type_key].workflow.workflow_name

        expected_context = {
            T.PROMPT_STUDIO_PROJECT: self.owner.email,
            T.WORKFLOW: self.owner.email,
            T.API_DEPLOYMENT: parent(T.API_DEPLOYMENT),
            T.ETL_PIPELINE: parent(T.ETL_PIPELINE),
            T.TASK_PIPELINE: parent(T.TASK_PIPELINE),
            T.ADAPTER: "LLM · openai",
            T.CONNECTOR: "minio",
        }
        for type_key, item in items.items():
            with self.subTest(type=type_key):
                result = results[type_key]
                self.assertEqual(result["context"], expected_context[type_key])
                expected_params = {"id": str(item.pk)}
                if type_key == T.ADAPTER:
                    expected_params["adapter_type"] = "LLM"
                self.assertEqual(
                    result["route"],
                    {"key": f"{type_key}.detail", "params": expected_params},
                )

    def test_owner_context_skips_service_accounts_and_takes_the_earliest(self) -> None:
        workflow = OSS_BUILDERS[T.WORKFLOW](self.org, self.owner, "theta-owned")
        service = make_user("svc-owner@example.com", is_service_account=True)
        # The service account is the earliest owner, so only the exclusion
        # skips it; the co-owner is inserted before the owner, so only the
        # created_at ordering (not heap order) picks the owner over it.
        for user in (service, self.coowner, self.owner):
            workflow.memberships.create(user=user, role=ResourceRole.OWNER)
        base = workflow.memberships.order_by("created_at").first().created_at
        for user, minutes in ((service, -2), (self.owner, -1), (self.coowner, 0)):
            workflow.memberships.filter(user=user).update(
                created_at=base + timedelta(minutes=minutes)
            )
        (group,) = search(self.admin, q="theta", types=T.WORKFLOW).data["groups"]
        self.assertEqual(group["results"][0]["context"], self.owner.email)
        # Same rule as the list's "Owned By" column.
        self.assertEqual(workflow.owner_email(), self.owner.email)

    def test_a_db_error_in_one_provider_does_not_poison_the_others(self) -> None:
        # TestCase wraps each test in a transaction, as ATOMIC_REQUESTS does.
        class Broken(SearchProvider):
            type_key, label, order = "broken", "Broken", 1

            def search(self, user, query, limit):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT * FROM no_such_table_for_search")
                return []

        workflow = OSS_BUILDERS[T.WORKFLOW](self.org, self.owner, "theta-flow")
        with patch(
            "global_search.views.get_providers",
            return_value=[Broken(), WorkflowProvider()],
        ):
            response = search(self.admin, allow_failures=True, q="theta")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["failed_types"], ["broken"])
        self.assertEqual(
            [r["id"] for g in response.data["groups"] for r in g["results"]],
            [str(workflow.pk)],
        )

    def test_mounted_on_tenant_path(self) -> None:
        # Importing the urlconf touches the DB, hence a TestCase.
        # OrganizationMiddleware strips the org segment before routing, so
        # /api/v1/unstract/<org>/search/ resolves as this path.
        match = resolve("/api/v1/unstract/search/")
        self.assertIs(match.func.view_class, GlobalSearchView)


def test_readme_lists_every_oss_type():
    for provider_cls in OSS_PROVIDERS:
        provider = provider_cls()
        row = f"| {provider.order} | `{provider.type_key}` | {provider.label} | `{provider.route_key}` |"
        assert row in README, f"README type table is missing: {row}"
