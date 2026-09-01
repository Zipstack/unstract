"""Request-level tests for the organisation-less ``whoami`` endpoint.

Everything that makes this endpoint work happens before the view: the route has
to survive `OrganizationMiddleware`, which reads the first path segment after
`unstract/` as an organisation and would otherwise take `whoami` for one, and
the organisation has to arrive from the key row rather than from the URL. None
of that is observable from the view in isolation, so these go through the real
URLconf and a real middleware chain.
"""

import secrets
import uuid

import pytest
from account_v2.models import Organization, User
from django.conf import settings
from django.test import override_settings
from django.urls import Resolver404, resolve
from platform_api.models import ApiKeyPermission, PlatformApiKey
from rest_framework.test import APITestCase

ORG_A = "org-a"
ORG_B = "org-b"

WHOAMI_URL = f"/{settings.PATH_PREFIX}/unstract/whoami/"

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


@pytest.mark.critical_path("platform-key-whoami")
@override_settings(MIDDLEWARE=_MIDDLEWARE)
class WhoAmITest(APITestCase):
    def setUp(self) -> None:
        self.org_a = Organization.objects.create(
            name=ORG_A, display_name="Org A", organization_id=ORG_A
        )
        self.org_b = Organization.objects.create(
            name=ORG_B, display_name="Org B", organization_id=ORG_B
        )

    @staticmethod
    def _make_user() -> User:
        email = f"svc-{uuid.uuid4().hex[:8]}@platform.internal"
        return User.objects.create_user(
            username=email, email=email, password=secrets.token_urlsafe()
        )

    def _make_key(self, organization=None, api_user=..., **kwargs) -> PlatformApiKey:
        # A fresh service account per key: api_user is a OneToOneField, so
        # sharing one across two keys in the same test is an IntegrityError.
        return PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=organization or self.org_a,
            api_user=self._make_user() if api_user is ... else api_user,
            **kwargs,
        )

    def _get(self, token: str | None = None, url: str = WHOAMI_URL):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return self.client.get(url, **headers)

    # --- routing -----------------------------------------------------------

    def test_the_route_is_reachable(self) -> None:
        """A 404 from the organisation regex eating `whoami` would otherwise
        look identical to a rejected request in every test below.
        """
        try:
            resolve(WHOAMI_URL)
        except Resolver404:  # pragma: no cover - the failure this guards
            self.fail(f"{WHOAMI_URL} resolves to nothing; the route is not mounted")

    def test_the_endpoint_is_not_whitelisted(self) -> None:
        """WHITELISTED_PATHS skips authentication entirely. This endpoint has
        nothing to say without a key, so landing there would make it answer
        with someone else's organisation or none at all.
        """
        assert not any(
            WHOAMI_URL.startswith(path) for path in settings.WHITELISTED_PATHS
        ), f"{WHOAMI_URL} is whitelisted — it would bypass authentication entirely"

    def test_the_organisation_middleware_still_defines_organisation_id(self) -> None:
        """The whitelist branch returns early. Downstream middleware reads the
        attribute directly, so leaving it unset is a 500 rather than a skip.
        """
        response = self._get(str(self._make_key().key))
        self.assertEqual(response.status_code, 200)

    # --- the answer --------------------------------------------------------

    def test_a_key_describes_itself(self) -> None:
        key = self._make_key(permission=ApiKeyPermission.READ)
        response = self._get(str(key.key))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "organization_id": ORG_A,
                "organization_name": "Org A",
                "permission": ApiKeyPermission.READ.value,
                "key_name": key.name,
            },
        )

    def test_the_organisation_comes_from_the_key_not_the_url(self) -> None:
        """The point of the endpoint: two keys, one URL, two answers."""
        key_a = self._make_key(organization=self.org_a)
        key_b = self._make_key(organization=self.org_b)

        self.assertEqual(self._get(str(key_a.key)).json()["organization_id"], ORG_A)
        self.assertEqual(self._get(str(key_b.key)).json()["organization_id"], ORG_B)

    def test_every_tier_can_read_its_own_identity(self) -> None:
        """The tier gates methods, not endpoints, and this is a GET."""
        for tier in ApiKeyPermission:
            with self.subTest(tier=tier.value):
                key = self._make_key(permission=tier)
                response = self._get(str(key.key))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["permission"], tier.value)

    # --- rejections --------------------------------------------------------

    def test_a_request_with_no_key_is_rejected(self) -> None:
        self.assertEqual(self._get().status_code, 401)

    def test_a_malformed_token_is_rejected(self) -> None:
        self.assertEqual(self._get("not-a-uuid").status_code, 401)

    def test_an_unknown_key_is_rejected(self) -> None:
        self.assertEqual(self._get(str(uuid.uuid4())).status_code, 401)

    def test_an_inactive_key_is_rejected(self) -> None:
        key = self._make_key(is_active=False)
        self.assertEqual(self._get(str(key.key)).status_code, 401)
