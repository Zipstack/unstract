"""The published contract matches what the endpoint serves.

* Real responses validate against the committed JSON Schema.
* Every registered OSS type, label and route key appears in the README's
  type table, so the documentation cannot drift from the code.
* The endpoint is mounted on the tenant path.
"""

import json
from pathlib import Path

import jsonschema
from django.test import TestCase
from django.urls import resolve
from permissions.tests.base import CoOwnerOrgTestMixin

from global_search.oss_providers import OSS_PROVIDERS
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
        owned = response.data["groups"][0]["results"][0]
        self.assertEqual(owned["context"], self.owner.email)

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
