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
from platform_api.whoami_views import WhoAmIView
from rest_framework.test import APIRequestFactory, APITestCase

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
        """The mount exists. Nothing more: `resolve()` runs no middleware, so
        this cannot see the organisation regex at all -- removing the whitelist
        entry leaves this test green. The middleware regression is covered by
        `test_the_organisation_middleware_still_defines_organisation_id`, and
        the failure it produces is a 403, not a 404.
        """
        try:
            resolve(WHOAMI_URL)
        except Resolver404:  # pragma: no cover - the failure this guards
            self.fail(f"{WHOAMI_URL} resolves to nothing; the route is not mounted")

    def test_the_endpoint_is_not_whitelisted(self) -> None:
        """WHITELISTED_PATHS skips authentication entirely, so `platform_api_key`
        would never be bound and every caller would get the view's own 401. The
        endpoint would stop working rather than leak -- but it would stop
        working silently, which this pins.
        """
        assert not any(
            WHOAMI_URL.startswith(path) for path in settings.WHITELISTED_PATHS
        ), f"{WHOAMI_URL} is whitelisted — it would bypass authentication entirely"

    def test_the_whitelist_does_not_swallow_paths_beneath_it(self) -> None:
        """`re.match` is a prefix test. Unanchored, an organisation literally
        named `whoami` would have every one of its paths treated as
        organisation-less.
        """
        import re

        beneath = f"/{settings.PATH_PREFIX}/unstract/whoami/workflow/"
        assert not any(
            re.match(pattern, beneath)
            for pattern in settings.ORGANIZATION_MIDDLEWARE_WHITELISTED_PATHS
        ), f"{beneath} is treated as organisation-less"

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

    def test_a_disallowed_method_returns_the_handler_shape(self) -> None:
        """The endpoint returns two error shapes, and this is the second one.

        A tier that permits POST gets past the middleware and is refused by
        DRF, in `{type, errors[]}` -- not the `{message}` the credential
        failures use.

        This asserts the wire only. It says nothing about the spec, and it does
        not fail if the spec stops describing this: the route serves GET, so
        OpenAPI has no operation to hang a POST response on. That gap is
        recorded on the PR rather than papered over with a test that reads as
        coverage it does not provide.
        """
        key = self._make_key(permission=ApiKeyPermission.READ_WRITE)

        response = self.client.post(WHOAMI_URL, HTTP_AUTHORIZATION=f"Bearer {key.key}")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(set(response.json()), {"type", "errors"})

    def test_a_tier_that_forbids_the_method_is_refused_earlier(self) -> None:
        """The 403 the middleware sends for the same request, so the two
        rejection paths for one method are pinned against each other rather
        than each looking like the only one.
        """
        key = self._make_key(permission=ApiKeyPermission.READ)

        response = self.client.post(WHOAMI_URL, HTTP_AUTHORIZATION=f"Bearer {key.key}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(response.json()), ["message"])

    def test_a_rejection_carries_the_body_the_spec_publishes(self) -> None:
        """The status alone was asserted everywhere above, and the status alone
        is what let the spec claim a body shape this route never sends.

        These rejections come from the middleware, not from DRF's exception
        handler, so the body is a bare `message` -- not the `{type, errors[]}`
        the organisation-scoped endpoints return.
        """
        response = self._get(str(uuid.uuid4()))

        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(response.json()), ["message"])

    def test_the_view_answers_401_when_no_key_reached_it(self) -> None:
        """The one rejection the view itself owns, and the only one the
        middleware cannot answer first: a session-authenticated caller with no
        platform key.

        Called directly, because every request that goes through the middleware
        is rejected before the view runs -- which is why this branch was
        uncovered while returning the wrong status. `raise NotAuthenticated`
        answers 403 here: DRF coerces it unless the first authenticator offers
        a WWW-Authenticate header, and SessionAuthentication offers none.
        """
        request = APIRequestFactory().get(WHOAMI_URL)
        response = WhoAmIView.as_view()(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(response.data), ["message"])

    # --- the organisation-scoped alias -------------------------------------

    def test_the_alias_under_an_organisation_segment_also_answers(self) -> None:
        """`OrganizationMiddleware` strips the segment, so `<org>/whoami/` is
        rewritten onto this same view. Untested, this behaviour would move the
        next time the org-match branch changed.

        Not mount order: swapping this mount below the tenant urlconf leaves
        every test here green, because no tenant urlconf declares `whoami/`.
        """
        key = self._make_key(organization=self.org_a)

        response = self._get(
            str(key.key), url=f"/{settings.PATH_PREFIX}/unstract/{ORG_A}/whoami/"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["organization_id"], ORG_A)

    def test_the_alias_rejects_a_key_from_another_organisation(self) -> None:
        """The alias is stricter than the documented route, not looser: naming
        an organisation re-arms the key-belongs-to-org check that the org-less
        form has nothing to check against.
        """
        key = self._make_key(organization=self.org_b)

        response = self._get(
            str(key.key), url=f"/{settings.PATH_PREFIX}/unstract/{ORG_A}/whoami/"
        )

        self.assertEqual(response.status_code, 403)
        # The 403 body is declared too, and "status asserted, body unasserted"
        # is exactly what let the original spec publish a shape nothing sends.
        self.assertEqual(list(response.json()), ["message"])
