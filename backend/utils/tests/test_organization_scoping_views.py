"""``filter_queryset_by_organization`` driven through the viewsets that use it.

test_organization_scoping pins the helper against a synthetic request. That
proves the helper fails closed, not that the ~15 production call sites reach it
with the context it needs, nor that a viewset opting out of
``OrganizationFilterBackend`` with ``skip_org_filter = True`` has anything left
scoping it.

These two viewsets are chosen because between them they cover both shapes the
call sites take: ``get_queryset()`` (five of the six internal viewsets) and a
``get_object()`` that deliberately bypasses ``get_queryset()`` for single-object
lookups (only FileExecutionInternalViewSet). On that viewset every single-object
operation — retrieve, update, partial update, destroy, and the ``status`` and
``update_hash`` actions — is driven cross-organization, and so is ``create``,
which scopes the parent execution rather than a file-execution pk. Each has an
own-organization control.

WebhookInternalViewSet is covered separately below because it is the one call
site whose model has no organization column to scope on.

``X-Organization-ID`` is what ``InternalAPIAuthMiddleware`` turns into
``request.organization_id``. The middleware warns and continues when the header
is absent, so "no organization_id attribute" is a reachable request state and is
tested as one.
"""

import secrets

import pytest
from account_v2.models import Organization
from django.test import TestCase
from notification_v2.enums import NotificationType
from notification_v2.internal_views import WebhookInternalViewSet
from notification_v2.models import Notification
from pipeline_v2.models import Pipeline
from rest_framework.test import APIRequestFactory
from workflow_manager.file_execution.internal_views import FileExecutionInternalViewSet
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_ABSENT = object()


@pytest.mark.django_db
class InternalViewSetOrgScopingTest(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.a = self._org_with_execution("a")
        self.b = self._org_with_execution("b")

    def _org_with_execution(self, tag: str):
        slug = f"org-{tag}-{secrets.token_hex(3)}"
        org = Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )
        workflow = Workflow._base_manager.create(
            workflow_name=f"wf-{slug}", organization=org
        )
        execution = WorkflowExecution._base_manager.create(
            workflow=workflow, status=ExecutionStatus.COMPLETED.value
        )
        file_execution = WorkflowFileExecution._base_manager.create(
            workflow_execution=execution,
            file_name=f"{slug}.pdf",
            status=ExecutionStatus.COMPLETED.value,
        )
        return org, workflow, execution, file_execution

    def _get(self, path: str, organization_id=_ABSENT):
        request = self.factory.get(path)
        # Set exactly what the middleware sets. Absent is a distinct state from
        # present-and-None, and production reads it with getattr(..., None).
        if organization_id is not _ABSENT:
            request.organization_id = organization_id
        return request

    # --- get_queryset() path: five of the six internal viewsets -------------

    def _list_executions(self, organization_id=_ABSENT):
        view = WorkflowExecutionInternalViewSet.as_view({"get": "list"})
        return view(self._get("/internal/workflow-execution/", organization_id))

    def _execution_ids(self, response) -> set[str]:
        results = response.data
        if isinstance(results, dict):
            results = results.get("results", results.get("data", []))
        return {str(row["id"]) for row in results}

    def test_list_without_the_header_serves_no_rows(self):
        """The header is optional at the middleware, so this is reachable."""
        response = self._list_executions()
        assert response.status_code == 200, response.data
        assert self._execution_ids(response) == set()

    def test_list_with_an_unresolvable_org_serves_no_rows(self):
        response = self._list_executions("org-that-does-not-exist")
        assert response.status_code == 200, response.data
        assert self._execution_ids(response) == set()

    def test_list_serves_only_the_callers_own_org(self):
        _, _, execution_a, _ = self.a
        _, _, execution_b, _ = self.b

        response = self._list_executions(self.a[0].organization_id)

        assert response.status_code == 200, response.data
        ids = self._execution_ids(response)
        assert str(execution_a.id) in ids
        assert str(execution_b.id) not in ids

    # --- get_object() path: bypasses get_queryset(), scopes independently ---

    def _retrieve_file_execution(self, pk, organization_id=_ABSENT):
        view = FileExecutionInternalViewSet.as_view({"get": "retrieve"})
        request = self._get(f"/internal/file-execution/{pk}/", organization_id)
        return view(request, id=str(pk))

    def test_retrieve_without_the_header_is_refused(self):
        _, _, _, file_execution = self.a
        response = self._retrieve_file_execution(file_execution.id)
        assert response.status_code == 404, response.data

    def test_retrieve_of_another_orgs_pk_is_refused(self):
        """Org A's context against an org B id: the whole point of the helper."""
        _, _, _, file_execution_b = self.b

        response = self._retrieve_file_execution(
            file_execution_b.id, self.a[0].organization_id
        )

        assert response.status_code == 404, response.data

    def test_retrieve_of_own_row_still_works(self):
        """Without this, a viewset that refused everything would pass above."""
        _, _, _, file_execution_a = self.a

        response = self._retrieve_file_execution(
            file_execution_a.id, self.a[0].organization_id
        )

        assert response.status_code == 200, response.data
        assert str(response.data["id"]) == str(file_execution_a.id)

    # --- writes through get_object(): update, delete and the two actions ----
    #
    # Every single-object write on this viewset resolves its target through the
    # same get_object(), so the scoping above is what stands between a caller
    # and another organization's row. Retrieve alone does not prove that: each
    # write is driven here with org A's context against org B's id, and the
    # row is re-read afterwards so a 404 that still wrote would fail.

    def _send(self, method: str, action: str, pk, data=None, organization_id=_ABSENT):
        view = FileExecutionInternalViewSet.as_view({method: action})
        request = getattr(self.factory, method)(
            f"/internal/file-execution/{pk}/", data or {}, format="json"
        )
        if organization_id is not _ABSENT:
            request.organization_id = organization_id
        return view(request, id=str(pk))

    def _assert_b_untouched(self, file_execution_b) -> None:
        before = (
            file_execution_b.file_name,
            file_execution_b.status,
            file_execution_b.file_hash,
            file_execution_b.mime_type,
        )
        file_execution_b.refresh_from_db()
        after = (
            file_execution_b.file_name,
            file_execution_b.status,
            file_execution_b.file_hash,
            file_execution_b.mime_type,
        )
        assert after == before

    def test_partial_update_of_another_orgs_pk_is_refused(self):
        _, _, _, file_execution_b = self.b

        response = self._send(
            "patch",
            "partial_update",
            file_execution_b.id,
            {"file_name": "tampered.pdf"},
            self.a[0].organization_id,
        )

        assert response.status_code == 404, response.data
        self._assert_b_untouched(file_execution_b)

    def test_update_of_another_orgs_pk_is_refused(self):
        _, _, _, file_execution_b = self.b

        response = self._send(
            "put",
            "update",
            file_execution_b.id,
            {"file_name": "tampered.pdf", "status": ExecutionStatus.ERROR.value},
            self.a[0].organization_id,
        )

        assert response.status_code == 404, response.data
        self._assert_b_untouched(file_execution_b)

    def test_destroy_of_another_orgs_pk_is_refused(self):
        _, _, _, file_execution_b = self.b

        response = self._send(
            "delete", "destroy", file_execution_b.id, None, self.a[0].organization_id
        )

        assert response.status_code == 404, response.data
        assert WorkflowFileExecution._base_manager.filter(id=file_execution_b.id).exists()

    def test_destroy_without_the_header_is_refused(self):
        _, _, _, file_execution_a = self.a

        response = self._send("delete", "destroy", file_execution_a.id)

        assert response.status_code == 404, response.data
        assert WorkflowFileExecution._base_manager.filter(id=file_execution_a.id).exists()

    def test_status_update_of_another_orgs_pk_is_refused(self):
        _, _, _, file_execution_b = self.b

        response = self._send(
            "post",
            "status",
            file_execution_b.id,
            {"status": ExecutionStatus.ERROR.value, "error_message": "tampered"},
            self.a[0].organization_id,
        )

        assert response.status_code == 404, response.data
        self._assert_b_untouched(file_execution_b)

    def test_update_hash_of_another_orgs_pk_is_refused(self):
        _, _, _, file_execution_b = self.b

        response = self._send(
            "patch",
            "update_hash",
            file_execution_b.id,
            {"file_hash": "tampered", "mime_type": "text/plain"},
            self.a[0].organization_id,
        )

        assert response.status_code == 404, response.data
        self._assert_b_untouched(file_execution_b)

    # Controls: without these, a viewset that refused every write would pass
    # all of the above.

    def test_partial_update_of_own_row_still_works(self):
        _, _, _, file_execution_a = self.a

        response = self._send(
            "patch",
            "partial_update",
            file_execution_a.id,
            {"file_name": "renamed.pdf"},
            self.a[0].organization_id,
        )

        assert response.status_code == 200, response.data
        file_execution_a.refresh_from_db()
        assert file_execution_a.file_name == "renamed.pdf"

    def test_update_of_own_row_still_works(self):
        _, _, _, file_execution_a = self.a

        response = self._send(
            "put",
            "update",
            file_execution_a.id,
            {"file_name": "replaced.pdf", "status": ExecutionStatus.ERROR.value},
            self.a[0].organization_id,
        )

        assert response.status_code == 200, response.data
        file_execution_a.refresh_from_db()
        assert file_execution_a.file_name == "replaced.pdf"
        assert file_execution_a.status == ExecutionStatus.ERROR.value

    def test_status_update_of_own_row_still_works(self):
        _, _, _, file_execution_a = self.a

        response = self._send(
            "post",
            "status",
            file_execution_a.id,
            {"status": ExecutionStatus.ERROR.value, "error_message": "boom"},
            self.a[0].organization_id,
        )

        assert response.status_code == 200, response.data
        file_execution_a.refresh_from_db()
        assert file_execution_a.status == ExecutionStatus.ERROR.value

    def test_update_hash_of_own_row_still_works(self):
        _, _, _, file_execution_a = self.a

        response = self._send(
            "patch",
            "update_hash",
            file_execution_a.id,
            {"file_hash": "own-hash"},
            self.a[0].organization_id,
        )

        assert response.status_code == 200, response.data
        file_execution_a.refresh_from_db()
        assert file_execution_a.file_hash == "own-hash"

    def test_destroy_of_own_row_still_works(self):
        _, _, _, file_execution_a = self.a

        response = self._send(
            "delete", "destroy", file_execution_a.id, None, self.a[0].organization_id
        )

        assert response.status_code == 204, response.data
        assert not WorkflowFileExecution._base_manager.filter(
            id=file_execution_a.id
        ).exists()

    # --- create: scopes the parent execution, not a file-execution pk -------

    def _create(self, execution, organization_id=_ABSENT):
        view = FileExecutionInternalViewSet.as_view({"post": "create"})
        request = self.factory.post(
            "/internal/file-execution/",
            {
                "execution_id": str(execution.id),
                "workflow_id": str(execution.workflow_id),
                "file_hash": {
                    "file_path": "/input/injected.pdf",
                    "file_name": "injected.pdf",
                    "file_hash": "injected-hash",
                },
            },
            format="json",
        )
        if organization_id is not _ABSENT:
            request.organization_id = organization_id
        return view(request)

    def _injected_rows(self, execution):
        return WorkflowFileExecution._base_manager.filter(
            workflow_execution=execution, file_hash="injected-hash"
        )

    def test_create_under_another_orgs_execution_is_refused(self):
        _, _, execution_b, _ = self.b

        response = self._create(execution_b, self.a[0].organization_id)

        assert response.status_code == 404, response.data
        assert not self._injected_rows(execution_b).exists()

    def test_create_without_the_header_is_refused(self):
        _, _, execution_a, _ = self.a

        response = self._create(execution_a)

        assert response.status_code == 404, response.data
        assert not self._injected_rows(execution_a).exists()

    def test_create_under_own_execution_still_works(self):
        _, _, execution_a, _ = self.a

        response = self._create(execution_a, self.a[0].organization_id)

        assert response.status_code == 201, response.data
        assert self._injected_rows(execution_a).count() == 1


@pytest.mark.django_db
class WebhookViewSetOrgScopingTest(TestCase):
    """The one scoped model that has no organization column of its own.

    ``Notification`` reaches an organization only through ``pipeline`` or
    ``api``. Routing it through ``filter_queryset_by_organization`` built
    ``.filter(organization=...)``, which raises ``FieldError`` — so with the
    header present this endpoint was a 500 either way, and without it the
    fail-closed change turned that into a silent zero rows. Neither is
    scoping, which is why this needs its own case rather than another
    parametrization above.
    """

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.a = self._org_with_notification("a")
        self.b = self._org_with_notification("b")

    def _org_with_notification(self, tag: str):
        slug = f"webhook-{tag}-{secrets.token_hex(3)}"
        org = Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )
        workflow = Workflow._base_manager.create(
            workflow_name=f"wf-{slug}", organization=org
        )
        pipeline = Pipeline._base_manager.create(
            pipeline_name=f"pl-{slug}", workflow=workflow, organization=org
        )
        notification = Notification._base_manager.create(
            name=f"hook-{slug}",
            url="https://example.com/hook",
            notification_type=NotificationType.WEBHOOK.value,
            pipeline=pipeline,
        )
        return org, pipeline, notification

    def _list(self, organization_id=_ABSENT):
        view = WebhookInternalViewSet.as_view({"get": "list"})
        request = self.factory.get("/internal/v1/webhook/")
        if organization_id is not _ABSENT:
            request.organization_id = organization_id
        return view(request)

    def _ids(self, response) -> set[str]:
        return {str(row["id"]) for row in response.data["notifications"]}

    def test_list_with_the_header_is_not_a_500(self):
        """The regression: .filter(organization=...) raised FieldError here."""
        response = self._list(self.a[0].organization_id)
        assert response.status_code == 200, response.data

    def test_list_serves_only_the_callers_own_org(self):
        response = self._list(self.a[0].organization_id)

        assert response.status_code == 200, response.data
        ids = self._ids(response)
        assert str(self.a[2].id) in ids
        assert str(self.b[2].id) not in ids

    def test_list_without_the_header_serves_no_rows(self):
        response = self._list()
        assert response.status_code == 200, response.data
        assert self._ids(response) == set()

    def test_list_with_an_unresolvable_org_serves_no_rows(self):
        response = self._list("org-that-does-not-exist")
        assert response.status_code == 200, response.data
        assert self._ids(response) == set()
