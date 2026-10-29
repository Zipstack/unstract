"""The drf-spectacular annotations are the published contract (with README.md),
so they must generate cleanly."""

from typing import Any

from adapter_processor_v2 import urls as adapter_urls
from connector_v2 import urls as connector_urls
from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator


def _schema(urls: Any) -> dict[str, Any]:
    schema: dict[str, Any] = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
        request=None, public=True
    )
    return schema


class SchemaContractTests(SimpleTestCase):
    def _assert_contract(self, urls: Any, profile: str) -> None:
        schema = _schema(urls)
        test_op = schema["paths"][f"/{profile}/{{id}}/test/"]["post"]
        self.assertEqual(test_op["operationId"], f"{profile}_test_and_record")
        self.assertNotIn("requestBody", test_op)
        self.assertEqual({"200", "403", "404"}, set(test_op["responses"]))

        body = schema["components"]["schemas"]["ConnectionCheckResult"]
        self.assertEqual(
            set(body["properties"]), {"status", "tested_at", "failure_reason"}
        )
        self.assertTrue(body["properties"]["failure_reason"]["nullable"])

        list_op = schema["paths"][f"/{profile}/"]["get"]
        params = {p["name"]: p for p in list_op["parameters"]}
        self.assertTrue({"failing", "last_test_status", "page", "page_size"} <= set(params))
        self.assertEqual(
            params["last_test_status"]["schema"]["enum"],
            ["connected", "failed", "never_tested"],
        )
        page_ref = list_op["responses"]["200"]["content"]["application/json"]["schema"]
        page = schema["components"]["schemas"][page_ref["$ref"].split("/")[-1]]
        self.assertIn("failing_count", page["properties"])

    def test_adapter_contract(self) -> None:
        self._assert_contract(adapter_urls, "adapter")

    def test_connector_contract(self) -> None:
        self._assert_contract(connector_urls, "connector")
