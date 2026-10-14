"""Response-time budget on a large organisation.

The contract budget is p95 <= 300 ms server time for all types at limit=5.
The merge gate is structural: a bounded number of SQL queries per type, and
the same number whatever the result count. Wall-clock time depends on the
runner, so the p95 is always printed but asserted only on request
(``GLOBAL_SEARCH_ASSERT_P95=1``, against ``GLOBAL_SEARCH_CEILING_MS``).

The fixture size stands in for the largest current organisation until real
counts are available: 2,000 rows per type, 200 users, 20 groups.
"""

import os
import statistics
import time

from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from permissions.roles import ResourceRole
from permissions.tests.base import _ADMIN_PREDICATE
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from tenant_account_v2.models import (
    GroupMembership,
    OrganizationGroup,
    OrganizationMember,
    ResourceGroupShare,
    ResourceMembership,
)
from unittest.mock import patch
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from global_search.oss_providers import OSS_PROVIDERS
from global_search.tests.base import search

ROWS_PER_TYPE = 2_000
USERS = 200
GROUPS = 20
BUDGET_MS = 300
ASSERT_P95 = os.environ.get("GLOBAL_SEARCH_ASSERT_P95") == "1"
CEILING_MS = int(os.environ.get("GLOBAL_SEARCH_CEILING_MS", str(BUDGET_MS)))
# Each type costs one ranked search query plus the organisation point
# lookups the existing ``for_user()`` makes (the org-scoped manager, and the
# membership subquery on the non-admin path). Anything per result -- an
# N+1 -- breaks the bound.
QUERIES_PER_TYPE = 3
# Headroom for an incidental per-request lookup.
FIXED_OVERHEAD_QUERIES = 2
# OSS types only, so the bound holds in every distribution; cloud types
# carry their own query bounds in the cloud repo.
OSS_TYPES = ",".join(p.type_key for p in OSS_PROVIDERS)
QUERIES = ["acme", "inv", "report", "zz", "pipe", "2024", "ac", "data"]
WORDS = ["invoice", "report", "acme", "data", "pipe", "ledger", "claims", "2024"]


def _name(prefix: str, i: int) -> str:
    return f"{WORDS[i % len(WORDS)]}-{prefix}-{i}"


class SearchBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = Organization.objects.create(
            name="big", display_name="Big", organization_id="org-big"
        )
        UserContext.set_organization_identifier(cls.org.organization_id)
        users = User.objects.bulk_create(
            User(username=f"u{i}@big.test", email=f"u{i}@big.test") for i in range(USERS)
        )
        OrganizationMember.objects.bulk_create(
            OrganizationMember(organization=cls.org, user=u, role="user") for u in users
        )
        groups = OrganizationGroup.objects.bulk_create(
            OrganizationGroup(organization=cls.org, name=f"g{i}", created_by=users[0])
            for i in range(GROUPS)
        )
        GroupMembership.objects.bulk_create(
            GroupMembership(group=groups[i % GROUPS], user=u) for i, u in enumerate(users)
        )
        cls.member = users[0]
        cls.admin = users[1]

        common = {"organization": cls.org}
        n = range(ROWS_PER_TYPE)
        parents = Workflow.objects.bulk_create(
            Workflow(workflow_name=f"parent-{i}", **common) for i in range(ROWS_PER_TYPE)
        )
        rows = [
            *Workflow.objects.bulk_create(
                Workflow(workflow_name=_name("wf", i), description=_name("d", i), **common)
                for i in n
            ),
            *CustomTool.objects.bulk_create(
                CustomTool(
                    tool_name=_name("tool", i),
                    description=_name("d", i),
                    author="seed",
                    **common,
                )
                for i in n
            ),
            *APIDeployment.objects.bulk_create(
                APIDeployment(
                    display_name=_name("api", i),
                    api_name=f"a{i}",
                    api_endpoint=f"deployment/api/org-big/a{i}/",
                    description=_name("d", i),
                    workflow=parents[i],
                    **common,
                )
                for i in n
            ),
            *Pipeline.objects.bulk_create(
                Pipeline(
                    pipeline_name=_name(f"p{t}", i),
                    pipeline_type=t,
                    workflow=parents[i],
                    **common,
                )
                for t in (Pipeline.PipelineType.ETL, Pipeline.PipelineType.TASK)
                for i in n
            ),
            *AdapterInstance.objects.bulk_create(
                AdapterInstance(
                    adapter_name=_name("ad", i),
                    adapter_id="openai|seed",
                    adapter_type="LLM",
                    adapter_metadata={},
                    description=_name("d", i),
                    **common,
                )
                for i in n
            ),
            *ConnectorInstance.objects.bulk_create(
                ConnectorInstance(connector_name=_name("conn", i), connector_id="minio|seed", **common)
                for i in n
            ),
        ]
        # One owner per row spread across users, a group share on every 50th
        # and an org share on every 100th: the non-admin path's real mix.
        memberships, shares = [], []
        for i, row in enumerate(rows):
            ct = ContentType.objects.get_for_model(type(row))
            memberships.append(
                ResourceMembership(
                    user=users[i % USERS],
                    role=ResourceRole.OWNER,
                    content_type=ct,
                    object_id=str(row.pk),
                    organization=cls.org,
                )
            )
            if i % 50 == 0:
                shares.append(
                    ResourceGroupShare(
                        group=groups[i % GROUPS],
                        content_type=ct,
                        object_id=str(row.pk),
                        organization=cls.org,
                    )
                )
            if i % 100 == 0:
                row.shared_to_org = True
        ResourceMembership.objects.bulk_create(memberships, batch_size=2_000)
        ResourceGroupShare.objects.bulk_create(shares, batch_size=2_000)
        for model in (Workflow, CustomTool, APIDeployment, Pipeline, AdapterInstance, ConnectorInstance):
            model.objects.filter(
                pk__in=[r.pk for r in rows if isinstance(r, model) and r.shared_to_org]
            ).update(shared_to_org=True)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE")

    def setUp(self) -> None:
        UserContext.set_organization_identifier(self.org.organization_id)
        patcher = patch(_ADMIN_PREDICATE, side_effect=lambda u: u.pk == self.admin.pk)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _queries(self, user: User, limit: int) -> list[str]:
        """SQL issued for one search, minus the per-provider savepoints the
        view opens inside a transaction (TestCase always has one)."""
        with CaptureQueriesContext(connection) as ctx:
            response = search(user, q="inv", types=OSS_TYPES, limit=limit)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["groups"])
        return [
            q["sql"]
            for q in ctx.captured_queries
            if not q["sql"].startswith(("SAVEPOINT", "RELEASE SAVEPOINT"))
        ]

    def _assert_bounded(self, user: User) -> None:
        search(user, q="warm", types=OSS_TYPES)  # content-type cache warm-up
        few = self._queries(user, limit=1)
        many = self._queries(user, limit=20)
        self.assertLessEqual(
            len(many),
            QUERIES_PER_TYPE * len(OSS_PROVIDERS) + FIXED_OVERHEAD_QUERIES,
            "\n".join(sql[:200] for sql in many),
        )
        # An N+1 shows up as more queries for more results.
        self.assertEqual(len(many), len(few))

    def _p95_ms(self, user: User) -> float:
        timings = []
        for _ in range(3):
            for q in QUERIES:
                start = time.perf_counter()
                search(user, q=q, types=OSS_TYPES)
                timings.append((time.perf_counter() - start) * 1000)
        return statistics.quantiles(timings, n=20)[-1]

    def test_query_count_is_bounded_per_type(self) -> None:
        for user in (self.member, self.admin):
            with self.subTest(user=user.email):
                self._assert_bounded(user)

    def test_p95_is_measured(self) -> None:
        for user in (self.member, self.admin):
            with self.subTest(user=user.email):
                p95 = self._p95_ms(user)
                print(f"[global_search budget] {user.email} p95={p95:.1f}ms (budget {BUDGET_MS}ms)")
                if ASSERT_P95:
                    self.assertLessEqual(p95, CEILING_MS)
