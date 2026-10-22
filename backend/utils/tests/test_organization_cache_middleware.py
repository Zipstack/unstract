"""The organization cache's seeding sites and request boundary, through a real
middleware chain (UN-4253).

``UserContext.set_organization`` seeds the cache only after the id is set, and a
seed that is lost reports nothing: the request simply pays the organization
lookup again. Only a request through the real chain, counting ``organization``
SELECTs, pins that the Bearer and internal-API paths seed. The last test pins
the request boundary: a whitelisted path that sets the id inside the view (as
the API-deployment helpers do) must not leave the cached row on the thread once
the response is closed.
"""

import secrets
import uuid

from account_v2.models import Organization, User
from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import path
from platform_api.models import PlatformApiKey
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response
from rest_framework.test import APITestCase
from workflow_manager.workflow_v2.models.workflow import Workflow

from utils.constants import Account
from utils.local_context import StateStore
from utils.user_context import UserContext

ORG = "org-cache"
INTERNAL_KEY = "internal-test-key"


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([])
def _scoped_view(request):
    """Evaluates an org-scoped default manager, which resolves the organization
    through ``UserContext.get_organization``.
    """
    return Response({"workflows": Workflow.objects.count()})


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([])
def _whitelisted_view(request):
    """What the API-deployment helpers do on a whitelisted path: set the id
    inside the view and never clear it.
    """
    UserContext.set_organization_identifier(ORG)
    UserContext.get_organization()
    return Response({"cached": StateStore.get(Account.ORGANIZATION_CACHE) is not None})


# OrganizationMiddleware strips the org segment before routing, so the Bearer
# view is registered on the stripped path while requests use the full one. The
# other two paths carry no org segment: ``/internal/`` is the internal API
# prefix, ``/health`` is in WHITELISTED_PATHS.
urlpatterns = [
    path("api/v1/unstract/scoped/", _scoped_view),
    path("internal/scoped/", _scoped_view),
    path("health/cache-probe/", _whitelisted_view),
]
BEARER_URL = f"/api/v1/unstract/{ORG}/scoped/"
INTERNAL_URL = "/internal/scoped/"
WHITELISTED_URL = "/health/cache-probe/"

# Trimmed from the production chain, preserving its relative order.
_MIDDLEWARE = [
    "middleware.request_id.CustomRequestIDMiddleware",
    settings.TENANT_MIDDLEWARE,
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    settings.CUSTOM_AUTH_MIDDLEWARE,
    "middleware.internal_api_auth.InternalAPIAuthMiddleware",
]


def _organization_lookups(queries) -> int:
    return sum(1 for q in queries if 'FROM "organization"' in q["sql"])


@override_settings(
    ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE, INTERNAL_SERVICE_API_KEY=INTERNAL_KEY
)
class OrganizationCacheMiddlewareTest(APITestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG, display_name="Org Cache", organization_id=ORG
        )
        service_account = User.objects.create_user(
            username="svc@example.com",
            email="svc@example.com",
            password=secrets.token_urlsafe(),
        )
        self.key = PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=self.org,
            api_user=service_account,
        )

    def tearDown(self) -> None:
        for key in (Account.ORGANIZATION_ID, Account.ORGANIZATION_CACHE):
            if hasattr(StateStore.thread_local, key):
                delattr(StateStore.thread_local, key)

    def test_bearer_path_seeds_the_cache_from_the_key(self):
        """The key's ``select_related("organization")`` is a JOIN, not a
        ``FROM "organization"`` statement, so a seeded request runs none.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                BEARER_URL, HTTP_AUTHORIZATION=f"Bearer {self.key.key}"
            )
        assert resp.status_code == 200, resp.content
        assert _organization_lookups(ctx.captured_queries) == 0

    def test_internal_api_path_seeds_the_cache_from_the_resolved_org(self):
        """The middleware's own ``resolve_organization`` is the one lookup; the
        view's org-scoped queryset must not add a second.
        """
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                INTERNAL_URL,
                HTTP_AUTHORIZATION=f"Bearer {INTERNAL_KEY}",
                HTTP_X_ORGANIZATION_ID=ORG,
            )
        assert resp.status_code == 200, resp.content
        assert _organization_lookups(ctx.captured_queries) == 1

    def test_whitelisted_path_does_not_leave_the_cache_on_the_thread(self):
        """No middleware sets or clears the id here, so only the request
        boundary (``request_finished``) can drop the row the view cached.
        """
        resp = self.client.get(WHITELISTED_URL)
        assert resp.status_code == 200, resp.content
        assert resp.json() == {"cached": True}
        assert StateStore.get(Account.ORGANIZATION_CACHE) is None
