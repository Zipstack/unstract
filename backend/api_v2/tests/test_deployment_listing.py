"""Request-level tests for listing an organisation's API deployments.

What makes a platform key work here sits either side of the view: the key
resolves to a service account, the organisation comes out of the path, and the
manager scopes the queryset to it. None of that is visible from the view alone,
so these go through the real URLconf and a real middleware chain.
"""

import secrets
import uuid

from account_v2.models import Organization, User
from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.services import create_api_user_for_key
from rest_framework.test import APITestCase
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

from api_v2.models import APIDeployment
from api_v2.serializers import APIDeploymentListSerializer

ORG_A = "org-a"
ORG_B = "org-b"


def listing_url(organization_id: str) -> str:
    return f"/{settings.PATH_PREFIX}/unstract/{organization_id}/api/deployment/"


# Trimmed from the production chain, preserving its relative order. The cloud
# test settings drop CustomAuthMiddleware, so pinning the list keeps this suite
# behaving the same in both trees.
_MIDDLEWARE = [
    "middleware.request_id.CustomRequestIDMiddleware",
    settings.TENANT_MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    settings.CUSTOM_AUTH_MIDDLEWARE,
]


@override_settings(MIDDLEWARE=_MIDDLEWARE)
class DeploymentListingTest(APITestCase):
    def setUp(self) -> None:
        self.org_a = Organization.objects.create(
            name=ORG_A, display_name="Org A", organization_id=ORG_A
        )
        self.org_b = Organization.objects.create(
            name=ORG_B, display_name="Org B", organization_id=ORG_B
        )
        self.deployment = self._make_deployment(
            self.org_a, api_name="invoices", description="Reads an invoice."
        )

    def tearDown(self) -> None:
        # Left set, this thread-local scopes the managers in whatever runs next.
        UserContext.set_organization_identifier(None)

    def _make_deployment(self, organization, **kwargs) -> APIDeployment:
        creator = self._make_user()
        workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}",
            organization=organization,
            created_by=creator,
        )
        # `save()` composes `api_endpoint` from the thread-local, not the row.
        UserContext.set_organization_identifier(organization.organization_id)
        try:
            return APIDeployment.objects.create(
                display_name=kwargs.pop("display_name", "Invoices"),
                workflow=workflow,
                organization=organization,
                created_by=creator,
                **kwargs,
            )
        finally:
            UserContext.set_organization_identifier(None)

    @staticmethod
    def _make_user() -> User:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
        return User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )

    def _make_key(self, organization=None, **kwargs) -> PlatformApiKey:
        key = PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=organization or self.org_a,
            **kwargs,
        )
        # The minting path, for the `is_service_account` flag it sets.
        create_api_user_for_key(key, key.organization)
        return key

    def _get(self, token: str | None = None, organization_id: str = ORG_A):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.get(listing_url(organization_id), **headers)

    def test_a_key_lists_its_organisations_deployments(self) -> None:
        response = self._get(str(self._make_key().key))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        (listed,) = body["results"]
        self.assertEqual(listed["api_name"], "invoices")
        self.assertEqual(listed["display_name"], "Invoices")
        self.assertEqual(listed["description"], "Reads an invoice.")
        self.assertEqual(listed["api_endpoint"], f"deployment/api/{ORG_A}/invoices/")

    def test_the_listing_carries_no_key_material(self) -> None:
        """A key readable here would widen a platform key into the ability to
        execute a deployment.
        """
        response = self._get(str(self._make_key().key))

        (listed,) = response.json()["results"]
        self.assertEqual(
            [field for field in listed if "key" in field.lower()],
            [],
            f"the listing published key material: {sorted(listed)}",
        )

    def test_a_read_only_key_may_list(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.READ)

        self.assertEqual(self._get(str(key.key)).status_code, 200)

    def test_an_organisation_with_nothing_deployed_lists_nothing(self) -> None:
        key = self._make_key(organization=self.org_b)

        response = self._get(str(key.key), organization_id=ORG_B)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_the_listing_is_scoped_to_the_organisation_not_the_installation(
        self,
    ) -> None:
        """Two organisations, one deployment each: a key sees its own."""
        self._make_deployment(self.org_b, api_name="receipts")
        key = self._make_key(organization=self.org_b)

        response = self._get(str(key.key), organization_id=ORG_B)

        self.assertEqual(
            [listed["api_name"] for listed in response.json()["results"]], ["receipts"]
        )

    def test_the_run_summary_matches_what_has_run(self) -> None:
        """The counts come from annotations on the list query rather than from
        a query per row, so they are worth reading back.
        """
        key = str(self._make_key().key)

        (listed,) = self._get(key).json()["results"]
        self.assertEqual(listed["run_count"], 0)
        self.assertIsNone(listed["last_run_time"])

        # Written without `save()`: the model's post-save hooks reach Redis,
        # which has nothing to do with what is being read back here.
        (execution,) = WorkflowExecution.objects.bulk_create(
            [
                WorkflowExecution(
                    pipeline_id=self.deployment.id, workflow=self.deployment.workflow
                )
            ]
        )

        (listed,) = self._get(key).json()["results"]
        self.assertEqual(listed["run_count"], 1)
        self.assertEqual(listed["last_run_time"], execution.created_at.isoformat())

        # The same serializer over a plain row, as `by_prompt_studio_tool`
        # serializes one: no annotations, same answer.
        unannotated = APIDeploymentListSerializer(self.deployment).data
        self.assertEqual(unannotated["run_count"], 1)
        self.assertEqual(unannotated["last_run_time"], execution.created_at.isoformat())

    def test_a_never_run_deployment_costs_no_extra_summary_query(self) -> None:
        """Its run annotations come back `None`, which still counts as annotated:
        reading the value rather than its presence sends every never-run row
        back to the database.
        """
        key = str(self._make_key().key)

        def executions(queries) -> int:
            return len(
                [query for query in queries if "workflow_execution" in query["sql"]]
            )

        with CaptureQueriesContext(connection) as one_row:
            self._get(key)
        for name in ("receipts", "contracts"):
            self._make_deployment(self.org_a, api_name=name)
        with CaptureQueriesContext(connection) as three_rows:
            self._get(key)

        # One per added row, for `last_5_run_statuses`, which is not annotated.
        self.assertEqual(executions(three_rows) - executions(one_row), 2)

    def test_paging_reaches_every_deployment_exactly_once(self) -> None:
        """Deployments that have never run all tie on the primary ordering, and
        each page is its own query: without a unique tie-breaker a page can
        repeat a row and drop another.
        """
        for name in ("receipts", "contracts"):
            self._make_deployment(self.org_a, api_name=name)
        key = str(self._make_key().key)

        seen = []
        for page in (1, 2, 3):
            response = self.client.get(
                f"{listing_url(ORG_A)}?page={page}&page_size=1",
                HTTP_AUTHORIZATION=f"Bearer {key}",
            )
            self.assertEqual(response.status_code, 200)
            seen += [listed["id"] for listed in response.json()["results"]]

        self.assertEqual(sorted(seen), sorted(set(seen)))
        self.assertEqual(len(seen), 3)

    def test_a_malformed_workflow_filter_is_a_bad_request(self) -> None:
        """Django raises on evaluation, which is past the point where a bad
        request can still be answered as one.
        """
        key = str(self._make_key().key)

        response = self.client.get(
            f"{listing_url(ORG_A)}?workflow=not-a-uuid",
            HTTP_AUTHORIZATION=f"Bearer {key}",
        )

        self.assertEqual(response.status_code, 400)

    def test_the_workflow_filter_selects_by_workflow(self) -> None:
        other = self._make_deployment(self.org_a, api_name="receipts")
        key = str(self._make_key().key)

        response = self.client.get(
            f"{listing_url(ORG_A)}?workflow={other.workflow_id}",
            HTTP_AUTHORIZATION=f"Bearer {key}",
        )

        self.assertEqual(
            [listed["api_name"] for listed in response.json()["results"]], ["receipts"]
        )

    def test_a_request_without_a_key_is_refused(self) -> None:
        self.assertEqual(self._get().status_code, 401)

    def test_an_unknown_key_is_refused(self) -> None:
        self.assertEqual(self._get(str(uuid.uuid4())).status_code, 401)

    def test_a_key_cannot_list_another_organisation(self) -> None:
        """The organisation is named in the path, so this is what stops a key
        reading across the installation.
        """
        key = self._make_key(organization=self.org_a)

        self.assertEqual(self._get(str(key.key), organization_id=ORG_B).status_code, 403)
