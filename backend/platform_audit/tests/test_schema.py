"""The drf-spectacular annotations are the published contract (with README.md),
so they must generate cleanly."""

from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator

from platform_audit import urls


class SchemaContractTests(SimpleTestCase):
    def test_schema_generates_every_operation(self) -> None:
        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        operations = {
            op["operationId"]
            for path in schema["paths"].values()
            for op in path.values()
        }
        self.assertEqual(
            operations,
            {
                "platform_audit_events_list",
                "platform_audit_events_export",
                "platform_audit_actions_list",
                "platform_audit_actors_list",
            },
        )
        page = schema["components"]["schemas"]["PlatformAuditEventPage"]
        self.assertIn("retention_days", page["properties"])
        list_op = schema["paths"]["/"]["get"]
        params = {p["name"] for p in list_op["parameters"]}
        self.assertTrue(
            {"action", "actor", "from", "to", "search", "page", "page_size"} <= params
        )
        self.assertNotIn("ordering", params)
        self.assertTrue({"200", "400", "403", "404"} <= set(list_op["responses"]))
        export = schema["paths"]["/export/"]["get"]["responses"]
        self.assertTrue({"200", "400", "403", "413"} <= set(export))
        self.assertIn("application/json", export["413"]["content"])
        for path in ("/actions/", "/actors/"):
            op = schema["paths"][path]["get"]
            self.assertIn("403", op["responses"])
            self.assertNotIn("ordering", {p["name"] for p in op.get("parameters", [])})
