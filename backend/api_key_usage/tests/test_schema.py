"""The drf-spectacular annotations are the published contract (with README.md),
so they must generate cleanly."""

from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator
from global_api_deployment_key import urls as global_urls
from platform_api import urls as platform_urls

from api_key_usage import urls as usage_urls

USAGE_FIELDS = {"last_used_at", "usage_status", "calls_30d"}


def _schema(urls) -> dict:
    return SchemaGenerator(patterns=urls.urlpatterns).get_schema(
        request=None, public=True
    )


def _response(schema: dict, path: str, method: str = "get") -> dict:
    content = schema["paths"][path][method]["responses"]["200"]["content"]
    return content["application/json"]["schema"]


def _component(schema: dict, ref: dict) -> dict:
    return schema["components"]["schemas"][ref["$ref"].rsplit("/", 1)[-1]]


class SchemaContractTests(SimpleTestCase):
    def test_summary(self) -> None:
        schema = _schema(usage_urls)

        op = schema["paths"]["/summary/"]["get"]
        body = _component(schema, _response(schema, "/summary/"))

        self.assertEqual(op["operationId"], "api_key_usage_summary")
        self.assertEqual(
            set(body["properties"]),
            {"never_used", "expiring_7d", "idle_90d", "by_type"},
        )

    def test_platform_key_operations(self) -> None:
        schema = _schema(platform_urls)

        history = _component(schema, _response(schema, "/keys/{id}/history/"))
        rotate = schema["paths"]["/keys/{id}/rotate/"]["post"]
        listed = _component(schema, _response(schema, "/keys/")["items"])

        self.assertEqual(
            set(history["properties"]),
            {"key_id", "days", "total_calls", "last_used_at", "usage_status"},
        )
        self.assertIn("requestBody", rotate)
        self.assertTrue(USAGE_FIELDS <= set(listed["properties"]))
        status = _component(schema, listed["properties"]["usage_status"]["allOf"][0])
        self.assertEqual(
            status["enum"],
            ["expired", "expiring", "never_used", "idle", "active"],
        )

    def test_global_key_operations(self) -> None:
        schema = _schema(global_urls)

        callers = _response(schema, "/keys/{id}/callers/")
        caller = _component(schema, callers["items"])
        detail = _component(schema, _response(schema, "/keys/{id}/"))

        self.assertEqual(callers["type"], "array")
        self.assertEqual(
            set(caller["properties"]),
            {"api_deployment_id", "display_name", "api_name", "calls", "last_call_at"},
        )
        self.assertIn("/keys/{id}/history/", schema["paths"])
        self.assertTrue(
            USAGE_FIELDS | {"previous_key_expires_at"} <= set(detail["properties"])
        )
