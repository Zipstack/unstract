"""Request-level tests for the Platform API key branch of CustomAuthMiddleware.

This branch is the only way a caller authenticates without a session, and it
carries authorization decisions the views behind it do not repeat: the key must
belong to the organization named in the URL, and its permission tier must allow
the HTTP method. Both are answered before the view runs, so they can only be
tested through a real middleware chain.
"""

import secrets
import uuid

from account_v2.models import Organization, User
from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import path
from platform_api.models import ApiKeyPermission, PlatformApiKey
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response
from rest_framework.test import APIClient, APITestCase

ORG_A = "org-a"
ORG_B = "org-b"


@api_view(["GET", "POST", "DELETE"])
@authentication_classes([SessionAuthentication])
@permission_classes([])
def _echo_view(request):
    """Reports what the middleware bound to the request."""
    key = getattr(request, "platform_api_key", None)
    return Response(
        {
            "user": getattr(request.user, "email", None),
            "key_id": str(key.id) if key else None,
        }
    )


# OrganizationMiddleware strips the org segment before routing, so the view is
# registered on the stripped path while requests are made against the full one.
urlpatterns = [path("api/v1/unstract/echo/", _echo_view)]
ECHO_URL = f"/api/v1/unstract/{ORG_A}/echo/"

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


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class PlatformKeyMiddlewareTest(APITestCase):
    def setUp(self) -> None:
        self.org_a = Organization.objects.create(
            name=ORG_A, display_name="Org A", organization_id=ORG_A
        )
        self.org_b = Organization.objects.create(
            name=ORG_B, display_name="Org B", organization_id=ORG_B
        )
        self.service_account = self._make_user("svc-a@example.com")

    @staticmethod
    def _make_user(email: str) -> User:
        return User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )

    def _make_key(self, organization=None, api_user=..., **kwargs) -> PlatformApiKey:
        return PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=organization or self.org_a,
            api_user=self.service_account if api_user is ... else api_user,
            **kwargs,
        )

    def _get(self, token: str, method: str = "get", url: str = ECHO_URL):
        return getattr(self.client, method)(url, HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_malformed_token_is_rejected(self) -> None:
        resp = self._get("not-a-uuid")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid API key format", resp.json()["message"])

    def test_unknown_key_is_rejected(self) -> None:
        resp = self._get(str(uuid.uuid4()))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid or inactive API key", resp.json()["message"])

    def test_inactive_key_is_rejected(self) -> None:
        key = self._make_key(is_active=False)
        resp = self._get(str(key.key))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid or inactive API key", resp.json()["message"])

    def test_key_from_another_organization_is_rejected(self) -> None:
        key = self._make_key(organization=self.org_b)
        resp = self._get(str(key.key))
        self.assertEqual(resp.status_code, 403)
        self.assertIn("does not belong to this organization", resp.json()["message"])

    def test_key_without_service_account_is_rejected(self) -> None:
        key = self._make_key(api_user=None)
        resp = self._get(str(key.key))
        self.assertEqual(resp.status_code, 401)
        self.assertIn("service account is missing", resp.json()["message"])

    def test_unrecognized_permission_tier_cannot_reach_the_middleware(self) -> None:
        """The tier is constrained in the database, so the middleware's own
        guard against an unknown tier is unreachable by design."""
        key = self._make_key()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PlatformApiKey.objects.filter(pk=key.pk).update(permission="superuser")

    def test_read_tier_allows_get(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.READ)
        self.assertEqual(self._get(str(key.key)).status_code, 200)

    def test_read_tier_rejects_post(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.READ)
        resp = self._get(str(key.key), method="post")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("does not allow POST", resp.json()["message"])

    def test_read_write_tier_rejects_delete(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.READ_WRITE)
        resp = self._get(str(key.key), method="delete")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("does not allow DELETE", resp.json()["message"])

    def test_full_access_tier_allows_delete(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.FULL_ACCESS)
        resp = self._get(str(key.key), method="delete")
        self.assertEqual(resp.status_code, 200)

    def test_accepted_key_binds_service_account_and_key(self) -> None:
        key = self._make_key()
        resp = self._get(str(key.key))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(),
            {"user": self.service_account.email, "key_id": str(key.id)},
        )

    def test_bearer_request_bypasses_csrf(self) -> None:
        """Bearer callers hold no CSRF token; the branch opts them out."""
        key = self._make_key(permission=ApiKeyPermission.READ_WRITE)
        client = APIClient(enforce_csrf_checks=True)
        resp = client.post(ECHO_URL, HTTP_AUTHORIZATION=f"Bearer {key.key}")
        self.assertEqual(resp.status_code, 200)
