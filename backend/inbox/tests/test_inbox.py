"""Inbox storage, endpoints and the share event."""

from datetime import timedelta
from unittest.mock import patch

from account_v2.models import Organization
from django.test import TestCase
from django.utils import timezone
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin, make_user
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import GroupMembership, OrganizationGroup
from tenant_account_v2.shareable_resources import descriptor_for_kind, kind_for_instance
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from inbox import events, service
from inbox.models import InboxItem
from inbox.views import InboxViewSet


def _items(user) -> list[InboxItem]:
    return list(InboxItem.objects.filter(user=user))


def _shape(index_or_constraint) -> tuple:
    return (
        index_or_constraint.name,
        tuple(getattr(index_or_constraint, "fields", ())),
        str(getattr(index_or_constraint, "check", "")),
    )


class ServiceTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()

    def notify(self, users, key="k1", **kwargs) -> None:
        service.notify(
            users,
            kind=InboxItem.Kind.RESOURCE_SHARED,
            title=kwargs.pop("title", "t"),
            dedupe_key=key,
            **kwargs,
        )

    def test_one_item_per_user(self) -> None:
        self.notify([self.viewer, self.outsider])
        self.assertEqual(len(_items(self.viewer)), 1)
        self.assertEqual(len(_items(self.outsider)), 1)
        self.assertEqual(_items(self.viewer)[0].organization, self.org)

    def test_same_event_twice_creates_no_duplicate(self) -> None:
        self.notify([self.viewer])
        self.notify([self.viewer])
        self.assertEqual(len(_items(self.viewer)), 1)

    def test_notify_needs_an_organization(self) -> None:
        UserContext.set_organization_identifier(None)
        with self.assertRaises(ValueError):
            self.notify([self.viewer])

    def test_long_title_is_cut_to_the_column(self) -> None:
        self.notify([self.viewer], title="x" * 300)
        self.assertEqual(len(_items(self.viewer)[0].title), 255)

    def test_unread_count_is_per_user_and_organization(self) -> None:
        self.notify([self.viewer], key="a")
        self.notify([self.viewer], key="b")
        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        InboxItem.objects.create(
            organization=other,
            user=self.viewer,
            kind="resource_shared",
            title="x",
            dedupe_key="c",
        )
        self.assertEqual(service.unread_count(self.viewer), 2)
        self.assertEqual(service.unread_count(self.outsider), 0)


class EndpointTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.factory = APIRequestFactory()
        for key in ("old", "new"):
            service.notify(
                [self.viewer],
                kind=InboxItem.Kind.RESOURCE_SHARED,
                title=key,
                body=f"{key} body",
                route={"key": "workflow.detail", "params": {"id": "w1"}},
                dedupe_key=key,
            )
        service.notify(
            [self.outsider],
            kind=InboxItem.Kind.RESOURCE_SHARED,
            title="theirs",
            dedupe_key="x",
        )

    def call(self, user, action, method="get", pk=None, data=None):
        view = InboxViewSet.as_view({method: action})
        request = getattr(self.factory, method)("/x/", data, format="json")
        force_authenticate(request, user=user)
        return view(request, pk=pk) if pk else view(request)

    def other_org_item(self) -> InboxItem:
        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        return InboxItem.objects.create(
            organization=other,
            user=self.viewer,
            kind="resource_shared",
            title="elsewhere",
            dedupe_key="e",
        )

    def test_list_is_newest_first_own_items_with_unread_count(self) -> None:
        response = self.call(self.viewer, "list")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 2)
        self.assertEqual(response.data["count"], 2)
        rows = response.data["results"]
        self.assertEqual([r["title"] for r in rows], ["new", "old"])
        self.assertEqual(
            set(rows[0]), {"id", "kind", "title", "body", "route", "created", "read"}
        )
        self.assertEqual(
            rows[0]["route"], {"key": "workflow.detail", "params": {"id": "w1"}}
        )
        self.assertFalse(rows[0]["read"])

    def test_list_excludes_other_organizations(self) -> None:
        self.other_org_item()
        titles = [r["title"] for r in self.call(self.viewer, "list").data["results"]]
        self.assertNotIn("elsewhere", titles)

    def test_cannot_read_own_item_in_another_organization(self) -> None:
        elsewhere = self.other_org_item()
        response = self.call(self.viewer, "read", "post", pk=str(elsewhere.pk))
        self.assertEqual(response.status_code, 404)
        elsewhere.refresh_from_db()
        self.assertIsNone(elsewhere.read_at)

    def test_read_all_leaves_other_organizations_unread(self) -> None:
        elsewhere = self.other_org_item()
        self.call(self.viewer, "read_all", "post")
        elsewhere.refresh_from_db()
        self.assertIsNone(elsewhere.read_at)

    def test_read_all_with_nothing_unread_pushes_nothing(self) -> None:
        self.call(self.viewer, "read_all", "post")
        with patch("inbox.views.push_unread") as push:
            self.call(self.viewer, "read_all", "post")
        push.assert_not_called()

    def test_mark_one_read(self) -> None:
        item = InboxItem.objects.get(user=self.viewer, title="new")
        response = self.call(self.viewer, "read", "post", pk=str(item.pk))
        self.assertEqual(response.status_code, 204)
        item.refresh_from_db()
        self.assertIsNotNone(item.read_at)
        self.assertEqual(self.call(self.viewer, "list").data["unread_count"], 1)

    def test_cannot_read_someone_elses_item(self) -> None:
        theirs = InboxItem.objects.get(user=self.outsider)
        response = self.call(self.viewer, "read", "post", pk=str(theirs.pk))
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertIsNone(theirs.read_at)

    def test_anonymous_request_is_refused(self) -> None:
        response = InboxViewSet.as_view({"get": "list"})(self.factory.get("/x/"))
        self.assertIn(response.status_code, (401, 403))

    def listed(self, title: str) -> dict:
        rows = self.call(self.viewer, "list").data["results"]
        return next(row for row in rows if row["title"] == title)

    def test_read_of_the_listed_version_marks_it(self) -> None:
        row = self.listed("new")
        response = self.call(
            self.viewer, "read", "post", pk=row["id"], data={"created": row["created"]}
        )
        self.assertEqual(response.status_code, 204)
        self.assertIsNotNone(InboxItem.objects.get(pk=row["id"]).read_at)

    def test_read_after_a_refresh_the_client_has_not_seen_is_refused(self) -> None:
        row = self.listed("new")
        # A later failure refreshes the item after the client listed it.
        InboxItem.objects.filter(pk=row["id"]).update(
            title="newer", created_at=timezone.now() + timedelta(seconds=1)
        )
        response = self.call(
            self.viewer, "read", "post", pk=row["id"], data={"created": row["created"]}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["item"]["title"], "newer")
        self.assertFalse(response.data["item"]["read"])
        self.assertEqual(response.data["unread_count"], 2)
        self.assertIsNone(InboxItem.objects.get(pk=row["id"]).read_at)

    def test_read_without_created_marks_the_current_version(self) -> None:
        item = InboxItem.objects.get(user=self.viewer, title="new")
        InboxItem.objects.filter(pk=item.pk).update(
            created_at=timezone.now() + timedelta(seconds=1)
        )
        response = self.call(self.viewer, "read", "post", pk=str(item.pk))
        self.assertEqual(response.status_code, 204)
        item.refresh_from_db()
        self.assertIsNotNone(item.read_at)

    def test_read_with_a_malformed_created_is_a_bad_request(self) -> None:
        item = InboxItem.objects.get(user=self.viewer, title="new")
        response = self.call(
            self.viewer, "read", "post", pk=str(item.pk), data={"created": "soon"}
        )
        self.assertEqual(response.status_code, 400)

    def test_reading_a_read_item_keeps_its_read_time(self) -> None:
        item = InboxItem.objects.get(user=self.viewer, title="new")
        self.call(self.viewer, "read", "post", pk=str(item.pk))
        first = InboxItem.objects.get(pk=item.pk).read_at
        self.call(self.viewer, "read", "post", pk=str(item.pk))
        self.assertEqual(InboxItem.objects.get(pk=item.pk).read_at, first)

    def test_mark_all_read_touches_only_own_items(self) -> None:
        response = self.call(self.viewer, "read_all", "post")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.call(self.viewer, "list").data["unread_count"], 0)
        self.assertEqual(self.call(self.outsider, "list").data["unread_count"], 1)


class ShareEventTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.group = OrganizationGroup.objects.create(
            organization=self.org, name="Team", created_by=self.owner
        )
        GroupMembership.objects.create(group=self.group, user=self.outsider)
        GroupMembership.objects.create(group=self.group, user=self.owner)
        self.addCleanup(UserContext.set_organization_identifier, None)

    def share(self, payload: dict):
        view = WorkflowViewSet.as_view({"post": "share"})
        request = APIRequestFactory().post("/x/", payload, format="json")
        force_authenticate(request, user=self.owner)
        return view(request, pk=str(self.workflow.pk))

    def test_direct_share_notifies_the_new_user_once(self) -> None:
        self.assertEqual(self.share({"shared_users": [self.viewer.pk]}).status_code, 200)
        (item,) = _items(self.viewer)
        self.assertEqual(item.kind, InboxItem.Kind.RESOURCE_SHARED)
        self.assertIn("wf-1", item.title)
        self.assertEqual(
            item.route,
            {"key": "workflow.detail", "params": {"id": str(self.workflow.pk)}},
        )
        # Sharing again with the same list changes nothing, so no new item.
        self.share({"shared_users": [self.viewer.pk]})
        self.assertEqual(len(_items(self.viewer)), 1)

    def test_group_share_notifies_members_but_not_the_actor(self) -> None:
        self.share({"shared_groups": [self.group.pk]})
        self.assertEqual(len(_items(self.outsider)), 1)
        self.assertEqual(_items(self.owner), [])
        self.assertEqual(_items(self.viewer), [])

    def test_user_in_both_a_group_and_the_direct_list_gets_one_item(self) -> None:
        self.share({"shared_users": [self.outsider.pk], "shared_groups": [self.group.pk]})
        self.assertEqual(len(_items(self.outsider)), 1)

    def test_unshare_creates_nothing(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.share({"shared_users": []})
        self.assertEqual(_items(self.viewer), [])

    def test_inbox_failure_does_not_fail_the_share(self) -> None:
        with patch("inbox.events.notify", side_effect=RuntimeError("boom")):
            with self.assertLogs("inbox.events", "ERROR"):
                response = self.share({"shared_users": [self.viewer.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.viewer, self.workflow.viewers())

    def test_direct_share_skips_users_who_already_had_access(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        with patch("inbox.events.notify") as notify:
            events.notify_resource_shared(
                resource=self.workflow,
                users=[self.viewer, self.outsider],
                groups=[],
                actor=self.owner,
                had_access=events.users_with_access(self.workflow),
            )
        (recipients,) = notify.call_args.args
        self.assertEqual(recipients, {self.outsider})

    def test_had_access_must_be_passed(self) -> None:
        with self.assertRaises(TypeError):
            events.notify_resource_shared(
                resource=self.workflow, users=[self.viewer], groups=[], actor=self.owner
            )

    def test_group_share_skips_members_who_already_had_access(self) -> None:
        self.workflow.memberships.create(user=self.outsider, role=ResourceRole.VIEWER)
        self.share({"shared_groups": [self.group.pk]})
        self.assertEqual(_items(self.outsider), [])

    def test_share_of_an_org_wide_resource_still_notifies(self) -> None:
        self.workflow.shared_to_org = True
        self.workflow.save(update_fields=["shared_to_org"])
        self.share({"shared_users": [self.viewer.pk]})
        self.assertEqual(len(_items(self.viewer)), 1)

    def test_unknown_prior_access_notifies_nobody(self) -> None:
        with patch(
            "tenant_account_v2.sharing_helpers.retained_user_ids",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("inbox.events", "ERROR") as logs:
                response = self.share({"shared_users": [self.viewer.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_items(self.viewer), [])
        # Skipped outright, not failed further down.
        self.assertEqual(len(logs.records), 1)

    def test_failed_insert_leaves_the_callers_transaction_usable(self) -> None:
        from django.db import connection, transaction

        def break_transaction(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1/0")

        with transaction.atomic():
            with patch.object(
                InboxItem.objects, "bulk_create", side_effect=break_transaction
            ):
                with self.assertLogs("inbox.events", "ERROR"):
                    events.notify_resource_shared(
                        resource=self.workflow,
                        users=[self.viewer],
                        groups=[],
                        actor=self.owner,
                        had_access=set(),
                    )
            self.assertTrue(Workflow.objects.filter(pk=self.workflow.pk).exists())

    def test_group_lookup_failure_still_tells_direct_users(self) -> None:
        with patch(
            "tenant_account_v2.group_notification_service._group_recipients_batch",
            side_effect=RuntimeError("boom"),
        ):
            with self.assertLogs("inbox.events", "ERROR"):
                self.share(
                    {"shared_users": [self.viewer.pk], "shared_groups": [self.group.pk]}
                )
        self.assertEqual(len(_items(self.viewer)), 1)

    def test_non_member_of_the_org_is_never_notified(self) -> None:
        stranger = make_user("s2@example.com")
        GroupMembership.objects.create(group=self.group, user=stranger)
        self.share({"shared_groups": [self.group.pk]})
        self.assertEqual(_items(stranger), [])


class SchemaTests(TestCase):
    def test_schema_documents_the_contract(self) -> None:
        from drf_spectacular.generators import SchemaGenerator

        from inbox import urls

        schema = SchemaGenerator(patterns=urls.urlpatterns).get_schema(
            request=None, public=True
        )
        ops = {
            op["operationId"] for path in schema["paths"].values() for op in path.values()
        }
        self.assertEqual(ops, {"inbox_list", "inbox_read", "inbox_read_all"})
        page = schema["components"]["schemas"]["InboxPage"]
        self.assertIn("unread_count", page["required"])
        item = schema["components"]["schemas"]["InboxItem"]
        self.assertEqual(
            set(item["properties"]),
            {"id", "kind", "title", "body", "route", "created", "read"},
        )
        self.assertTrue(item["properties"]["route"]["nullable"])
        self.assertEqual(item["properties"]["kind"], {"type": "string"})
        (op,) = (
            op
            for path in schema["paths"].values()
            for op in path.values()
            if op["operationId"] == "inbox_list"
        )
        body = op["responses"]["200"]["content"]["application/json"]["schema"]
        self.assertEqual(body, {"$ref": "#/components/schemas/InboxPage"})
        self.assertIn("404", op["responses"])
        results = page["properties"]["results"]["items"]
        self.assertEqual(results, {"$ref": "#/components/schemas/InboxItem"})
        (read,) = (
            op
            for path in schema["paths"].values()
            for op in path.values()
            if op["operationId"] == "inbox_read"
        )
        self.assertEqual(set(read["responses"]) & {"204", "404", "409"}, {"204", "404", "409"})
        conflict = read["responses"]["409"]["content"]["application/json"]["schema"]
        self.assertEqual(conflict, {"$ref": "#/components/schemas/InboxReadConflict"})
        route = schema["components"]["schemas"]["InboxRoute"]
        self.assertEqual(set(route["properties"]), {"key", "params"})


class RouteTests(TestCase):
    def test_route_for_each_shareable_kind(self) -> None:
        from types import SimpleNamespace

        from inbox.events import _route

        res = SimpleNamespace(pk="p1", pipeline_type="ETL", adapter_type="LLM")
        cases = {
            "workflow": {"key": "workflow.detail", "params": {"id": "p1"}},
            "pipeline": {"key": "etl_pipeline.detail", "params": {"id": "p1"}},
            "api_deployment": {"key": "api_deployment.detail", "params": {"id": "p1"}},
            "connector_instance": {"key": "connector.detail", "params": {"id": "p1"}},
            "adapter_instance": {
                "key": "adapter.info",
                "params": {"id": "p1", "adapter_type": "LLM"},
            },
            "custom_tool": {
                "key": "prompt_studio_project.detail",
                "params": {"id": "p1"},
            },
            "agentic_project": {"key": "agentic_project.detail", "params": {"id": "p1"}},
            "lookup": None,
        }
        for kind, expected in cases.items():
            self.assertEqual(_route(kind, res), expected, kind)
        task = SimpleNamespace(pk="p1", pipeline_type="TASK")
        self.assertEqual(_route("pipeline", task)["key"], "task_pipeline.detail")
        app = SimpleNamespace(pk="p1", pipeline_type="APP")
        self.assertIsNone(_route("pipeline", app))


class WiringTests(TestCase):
    def test_purge_path_the_worker_calls_resolves(self) -> None:
        from django.urls import resolve

        from inbox.internal_views import PurgeInboxAPIView

        match = resolve("/internal/v1/inbox/purge/")
        self.assertIs(match.func.view_class, PurgeInboxAPIView)

    def test_every_model_index_has_a_migration(self) -> None:
        # Tests run without migrations, so read the migration files themselves.
        import importlib
        import pkgutil

        import inbox.migrations as package

        migrated = set()
        for module in pkgutil.iter_modules(package.__path__):
            migration = importlib.import_module(f"inbox.migrations.{module.name}")
            for op in migration.Migration.operations:
                for attr in ("index", "constraint"):
                    if hasattr(op, attr):
                        migrated.add(_shape(getattr(op, attr)))
                options = getattr(op, "options", {})
                for item in options.get("indexes", []) + options.get("constraints", []):
                    migrated.add(_shape(item))
        for item in InboxItem._meta.indexes + InboxItem._meta.constraints:
            self.assertIn(_shape(item), migrated)


class ShareKindTests(CoOwnerOrgTestMixin, TestCase):
    """Each OSS kind through the real event: its label, name and route."""

    def setUp(self) -> None:
        self._seed_org()
        self.addCleanup(UserContext.set_organization_identifier, None)

    def test_every_oss_kind_names_the_resource_and_links_to_it(self) -> None:
        from permissions.tests.base import RESOURCE_SPECS

        # Written out, not read from the code's table, so a typo there fails here.
        expected = {
            "workflow": ("workflow", "workflow.detail"),
            "pipeline": ("pipeline", None),  # DEFAULT-type pipelines have no page
            "api_deployment": ("API deployment", "api_deployment.detail"),
            "connector_instance": ("connector", "connector.detail"),
            "adapter_instance": ("adapter", "adapter.info"),
            "custom_tool": ("Prompt Studio project", "prompt_studio_project.detail"),
        }
        for spec in RESOURCE_SPECS:
            with self.subTest(kind=spec.kind):
                resource = spec.build(self.org, self.owner)
                InboxItem.objects.all().delete()
                events.notify_resource_shared(
                    resource=resource,
                    users=[self.viewer],
                    groups=[],
                    actor=self.owner,
                    had_access=set(),
                )
                (item,) = _items(self.viewer)
                kind = kind_for_instance(resource)
                label, key = expected[kind]
                name = getattr(resource, descriptor_for_kind(kind).name_field)
                self.assertTrue(name)
                self.assertEqual(
                    item.title, f"{self.owner.email} shared the {label} {name} with you"
                )
                self.assertEqual(item.route and item.route["key"], key)
