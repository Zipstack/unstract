"""Critical path ``mcp-platform-auth``: the organization-scoped MCP endpoint
is authenticated by ``CustomAuthMiddleware``, not by the view.

That distinction is the whole point of these tests. The deployment MCP server
owns its own auth, so testing it through ``APIRequestFactory`` is sound. This
server does not — its credential is resolved by middleware, which
``APIRequestFactory`` and direct view calls bypass entirely. A test written
that way would pass against a completely unauthenticated endpoint.

So every test here goes through ``django.test.Client`` against the real tenant
URL, exercising the full middleware stack. Needs a live DB (integration tier).
"""

from __future__ import annotations

import json
import uuid

import pytest
from account_v2.models import Organization, User
from django.conf import settings
from django.test import Client, TestCase
from platform_api.models import PlatformApiKey
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

ORG_ID = "org-platform-mcp"
OTHER_ORG_ID = "org-platform-other"


def make_org_with_key(org_id: str, permission: str = "read_write"):
    """Create an organization and a platform key backed by a service account."""
    org = Organization.objects.create(
        name=org_id, display_name=org_id, organization_id=org_id
    )
    user = User.objects.create(
        username=f"svc-{org_id}",
        email=f"svc-{org_id}@platform.internal",
        user_id=f"uid-{org_id}",
        is_service_account=True,
    )
    OrganizationMember.objects.create(user=user, organization=org, role="user")
    key = PlatformApiKey.objects.create(
        name=f"key-{org_id}",
        description="test key",
        organization=org,
        api_user=user,
        permission=permission,
    )
    return org, user, key


def unmet_precondition() -> str | None:
    """Why this suite cannot run here, or None when it can.

    These tests assert that a credential is *rejected*. That only means
    anything if the endpoint exists and something is there to reject it — and
    neither is guaranteed outside the OSS tree, because both are settings-
    dependent and the settings differ downstream.

    Unstract Cloud is the live example of both halves. ``copy_cloud_deps``
    overwrites the OSS ``settings/test.py`` with a redirect to ``test_cloud``,
    which derives from ``settings/cloud`` — so this module's
    ``MCP_PLATFORM_SERVER_ENABLED = True`` never reaches it and ``urls_v2``
    leaves the route unmounted. That same file also drops
    ``CUSTOM_AUTH_MIDDLEWARE`` from the default test ``MIDDLEWARE``, and this
    view has ``permission_classes = []`` and deliberately does not
    re-authenticate — so without the middleware the endpoint is reachable with
    no credential at all.

    Checked as two explicit preconditions rather than by reading
    ``MCP_PLATFORM_SERVER_ENABLED``: the flag is what *causes* the mount in the
    OSS URLconf, but it is not what these tests need. They need the route and
    the middleware, and asking directly stays correct for any tree that mounts
    the server some other way.
    """
    from django.urls import Resolver404, resolve

    # The org segment is stripped from `path_info` by tenant middleware before
    # URL resolution, so the mounted pattern carries no org — resolving the URL
    # these tests request would 404 even on OSS, where they pass.
    try:
        resolve(f"/{settings.TENANT_SUBFOLDER_PREFIX}/mcp/")
    except Resolver404:
        return (
            f"the platform MCP route is not mounted in {settings.ROOT_URLCONF} "
            "(MCP_PLATFORM_SERVER_ENABLED is off, or this URLconf does not "
            "carry the mount), so every request here would 404"
        )

    if settings.CUSTOM_AUTH_MIDDLEWARE not in settings.MIDDLEWARE:
        return (
            f"{settings.CUSTOM_AUTH_MIDDLEWARE} is not in MIDDLEWARE, and this "
            "endpoint is authenticated by that middleware rather than by the "
            "view — every request would arrive unauthenticated"
        )

    return None


class PlatformMCPAuthTest(TestCase):
    def setUp(self) -> None:
        # Skipped loudly rather than left to fail, because the failure mode is
        # worse than a red test: with the route unmounted every request 404s,
        # and a 404 satisfies "this request is refused" just as well as the 401
        # being asserted. `test_bad_credentials_are_rejected` passed that way on
        # cloud — green for auth that was never reached. A skip names the gap.
        reason = unmet_precondition()
        if reason:
            self.skipTest(f"{reason}. See this module's docstring for why.")

        self.org, self.user, self.key = make_org_with_key(ORG_ID)
        _, _, self.other_key = make_org_with_key(OTHER_ORG_ID)
        UserContext.set_organization_identifier(ORG_ID)
        self.client = Client()
        self.url = f"/api/v1/unstract/{ORG_ID}/mcp/"

    def _post(self, auth: str | None = None, body: dict | None = None, url: str = None):
        """POST through the full URL stack so the auth middleware runs."""
        payload = (
            body
            if body is not None
            else {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            }
        )
        headers = {"HTTP_AUTHORIZATION": auth} if auth else {}
        return self.client.post(
            url or self.url,
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_bad_credentials_are_rejected(self) -> None:
        """Each of these must be refused before any tool is reachable.

        The middleware answers most of them, which is exactly what is being
        verified — that this endpoint sits behind it.
        """
        cases = [
            ("no authorization header", None),
            ("not a bearer token", f"Token {self.key.key}"),
            ("empty bearer", "Bearer "),
            ("malformed uuid", "Bearer not-a-uuid"),
            ("unknown key", f"Bearer {uuid.uuid4()}"),
            ("key from another organization", f"Bearer {self.other_key.key}"),
        ]
        for label, auth in cases:
            with self.subTest(label):
                response = self._post(auth)
                assert response.status_code in (
                    401,
                    403,
                ), f"{label}: got {response.status_code}, body={response.content[:200]}"

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_inactive_key_is_rejected(self) -> None:
        self.key.is_active = False
        self.key.save()

        response = self._post(f"Bearer {self.key.key}")

        assert response.status_code == 401, response.content

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_read_tier_key_cannot_reach_the_server(self) -> None:
        """A documented limitation, pinned so it cannot change silently.

        The middleware's tier check gates on HTTP method and every JSON-RPC
        message arrives as a POST whatever the tool inside it does, so a `read`
        key is refused outright — even though this server exposes plenty of
        read tools.
        """
        self.key.permission = "read"
        self.key.save()

        response = self._post(f"Bearer {self.key.key}")

        assert response.status_code == 403, response.content

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_valid_key_reaches_the_tool_listing(self) -> None:
        """The inverse guard: a check that refused everything would satisfy
        every rejection case above.
        """
        response = self._post(f"Bearer {self.key.key}")

        assert response.status_code == 200, response.content
        tools = [t["name"] for t in json.loads(response.content)["result"]["tools"]]

        # readMeFirst must lead: agents weight earlier tools more heavily, and
        # it is what explains the budget and the org-wide reach of the rest.
        assert tools[0] == "readMeFirst"
        # A representative tool from each group, rather than the full ordered
        # list — pinning all 19 makes this fail on every addition without
        # telling anyone anything useful.
        assert {
            "whoami",
            "listApiDeployments",
            "listExecutions",
            "getUsageSummary",
            "setApiDeploymentActive",
            "executePipeline",
            "bulkFetchResponse",
        } <= set(tools)

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_the_endpoint_is_not_whitelisted(self) -> None:
        """Guards the placement this server's security depends on.

        If these URLs were ever moved under the whitelisted ``/mcp/`` prefix,
        ``CustomAuthMiddleware`` would skip them and the endpoint would answer
        unauthenticated callers. An unauthenticated request must not get a
        JSON-RPC result.
        """
        from django.conf import settings

        assert not any(
            self.url.startswith(path) for path in settings.WHITELISTED_PATHS
        ), f"{self.url} is whitelisted — it would bypass authentication entirely"

        response = self._post(auth=None)
        assert response.status_code in (401, 403)
        assert b'"result"' not in response.content

    @pytest.mark.critical_path("mcp-platform-auth")
    def test_org_in_url_must_match_the_key(self) -> None:
        """A valid key must not reach another organization's MCP endpoint."""
        response = self._post(
            f"Bearer {self.key.key}", url=f"/api/v1/unstract/{OTHER_ORG_ID}/mcp/"
        )

        assert response.status_code in (401, 403), response.content
