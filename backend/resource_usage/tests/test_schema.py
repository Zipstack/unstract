"""The drf-spectacular annotations are the published contract (with README.md)."""

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


class UsageSchemaTests(SimpleTestCase):
    def _assert_contract(
        self, urls: Any, profile: str, body: str, codes: set[str]
    ) -> dict[str, Any]:
        schema = _schema(urls)
        usage_op = schema["paths"][f"/{profile}/{{id}}/usage/"]["get"]
        self.assertEqual(usage_op["operationId"], f"{profile}_usage")
        self.assertEqual(codes, set(usage_op["responses"]))

        list_op = schema["paths"][f"/{profile}/"]["get"]
        params = {p["name"] for p in list_op["parameters"]}
        self.assertTrue({"with_usage", "unused", "failing", "page"} <= params)
        components = schema["components"]["schemas"]
        # The list's paged envelope declares unused_count, as optional.
        ref = list_op["responses"]["200"]["content"]["application/json"]["schema"]
        paged = components[ref["$ref"].rsplit("/", 1)[-1]]
        self.assertIn("unused_count", paged["properties"])
        self.assertNotIn("unused_count", paged["required"])
        # ``type`` is an open string: cloud groups and ``other`` add values.
        item = next(c for name, c in components.items() if name.endswith("UsageItem"))
        self.assertEqual(item["properties"]["type"]["type"], "string")
        self.assertNotIn("enum", item["properties"]["type"])
        properties: dict[str, Any] = components[body]["properties"]
        return properties

    def test_adapter_contract(self) -> None:
        props = self._assert_contract(
            adapter_urls, "adapter", "AdapterUsage", {"200", "403", "404"}
        )
        self.assertEqual(set(props), {"id", "used_in_count", "groups"})

    def test_connector_contract(self) -> None:
        props = self._assert_contract(
            connector_urls, "connector", "ConnectorUsage", {"200", "404"}
        )
        self.assertEqual(set(props), {"id", "used_in_count", "used_as", "groups"})
