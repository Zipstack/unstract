"""Last-used product preference and first-login flag (PB-T23).

* A new user has no product and ``has_chosen`` false; one PUT sets both.
* The preference belongs to the user: other users and other organisations do
  not see a different value, and service accounts are refused.
* ``session`` carries ``last_product`` and ``has_chosen`` beside its existing
  fields.
* Responses validate against the committed JSON Schemas, and the schemas'
  product list matches ``Product``.

Requests go through the real URLconf and middleware with the Django test
client, so routing and the auth middleware are covered too. The built-in
session auth is forced, so a distribution's auth plugin (cloud's Auth0) cannot
401 the request first, as in ``global_search/tests/test_contract.py``.

DB-backed Django ``TestCase`` → auto-marked ``integration`` by ``backend/conftest.py``.
"""

import json
import secrets
from pathlib import Path
from unittest import mock

import jsonschema
from django.test import TestCase

from account_v2.authentication_plugin_registry import AuthenticationPluginRegistry
from account_v2.enums import Product
from account_v2.models import User, UserProductPreference
from account_v2.product_preference import (
    get_product_preference,
    set_product_preference,
)

URL = "/api/v1/users/me/product-preference/"
SESSION_URL = "/api/v1/session"

CONTRACT = Path(__file__).parent / "contract"
RESPONSE_SCHEMA = json.loads(
    (CONTRACT / "product-preference-response.schema.json").read_text()
)
REQUEST_SCHEMA = json.loads(
    (CONTRACT / "product-preference-request.schema.json").read_text()
)
SESSION_SCHEMA = json.loads((CONTRACT / "session-product-fields.schema.json").read_text())
FORMATS = jsonschema.FormatChecker()

# The session fields that existed before PB-T23, from UserSessionResponseSerializer.
EXISTING_SESSION_FIELDS = {
    "id",
    "user_id",
    "email",
    "organization_id",
    "role",
    "provider",
    "is_staff",
    "disable_sso_idp_authorization",
}


class _BuiltInSessionAuth(TestCase):
    def setUp(self) -> None:
        no_plugin = mock.patch.object(
            AuthenticationPluginRegistry, "is_plugin_available", return_value=False
        )
        no_plugin.start()
        self.addCleanup(no_plugin.stop)


def _user(email: str, **fields) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe(), **fields
    )


class ProductPreferenceEndpointTests(_BuiltInSessionAuth):
    def setUp(self) -> None:
        super().setUp()
        self.user = _user("first@example.com")
        self.client.force_login(self.user)

    def _put(self, body: dict):
        return self.client.put(
            URL, data=json.dumps(body), content_type="application/json"
        )

    def _assert_contract(self, data: dict) -> None:
        jsonschema.validate(data, RESPONSE_SCHEMA, format_checker=FORMATS)

    def test_new_user_has_no_product_and_has_not_chosen(self) -> None:
        response = self.client.get(URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"product": None, "updated_at": None, "has_chosen": False}
        )
        self._assert_contract(response.json())

    def test_one_put_sets_product_and_clears_first_login_flag(self) -> None:
        response = self._put({"product": "llm-whisperer"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product"], "llm-whisperer")
        self.assertTrue(response.json()["has_chosen"])
        self.assertIsNotNone(response.json()["updated_at"])
        self._assert_contract(response.json())

        read = self.client.get(URL).json()
        self.assertEqual(read, response.json())

    def test_put_replaces_the_previous_product(self) -> None:
        self._put({"product": "llm-whisperer"})
        self._put({"product": "unstract"})

        self.assertEqual(self.client.get(URL).json()["product"], "unstract")
        self.assertEqual(UserProductPreference.objects.filter(user=self.user).count(), 1)

    def test_every_product_id_is_accepted(self) -> None:
        for product in Product.values:
            with self.subTest(product=product):
                jsonschema.validate({"product": product}, REQUEST_SCHEMA)
                response = self._put({"product": product})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["product"], product)

    def test_unknown_or_missing_product_is_rejected_and_nothing_is_stored(self) -> None:
        for body in ({"product": "photoshop"}, {"product": None}, {}):
            with self.subTest(body=body):
                self.assertEqual(self._put(body).status_code, 400)
        self.assertFalse(UserProductPreference.objects.filter(user=self.user).exists())

    def test_a_user_reads_and_writes_only_their_own_preference(self) -> None:
        self._put({"product": "llm-whisperer"})
        other = _user("other@example.com")
        self.client.force_login(other)

        self.assertFalse(self.client.get(URL).json()["has_chosen"])
        self._put({"product": "unstract"})

        self.assertEqual(get_product_preference(self.user).product, "llm-whisperer")
        self.assertEqual(get_product_preference(other).product, "unstract")

    def test_service_accounts_are_refused(self) -> None:
        bot = _user("bot@example.com", is_service_account=True)
        self.client.force_login(bot)

        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self._put({"product": "unstract"}).status_code, 403)
        self.assertFalse(UserProductPreference.objects.filter(user=bot).exists())

    def test_anonymous_request_is_unauthorised(self) -> None:
        self.client.logout()

        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_other_methods_are_not_allowed(self) -> None:
        self.assertEqual(self.client.post(URL, {"product": "unstract"}).status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)


class SessionProductFieldsTests(_BuiltInSessionAuth):
    def setUp(self) -> None:
        super().setUp()
        self.user = _user("session@example.com")
        self.client.force_login(self.user)

    def _session(self, organization: str | None = None) -> dict:
        if organization is not None:
            session = self.client.session
            session["organization"] = organization
            session.save()
        response = self.client.get(SESSION_URL)
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_new_user_session_has_no_product_and_has_not_chosen(self) -> None:
        data = self._session()

        self.assertIsNone(data["last_product"])
        self.assertFalse(data["has_chosen"])
        jsonschema.validate(data, SESSION_SCHEMA)

    def test_session_only_gains_the_two_new_fields(self) -> None:
        self.assertEqual(
            set(self._session()), EXISTING_SESSION_FIELDS | {"last_product", "has_chosen"}
        )

    def test_session_carries_the_stored_product_in_every_organisation(self) -> None:
        set_product_preference(self.user, "llm-whisperer")

        for organization in ("org_one", "org_two"):
            with self.subTest(organization=organization):
                data = self._session(organization)
                self.assertEqual(data["last_product"], "llm-whisperer")
                self.assertTrue(data["has_chosen"])
                self.assertEqual(data["organization_id"], organization)
                jsonschema.validate(data, SESSION_SCHEMA)


class ProductPreferenceServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = _user("service@example.com")

    def test_set_rejects_an_unknown_product(self) -> None:
        with self.assertRaises(ValueError):
            set_product_preference(self.user, "photoshop")
        self.assertFalse(get_product_preference(self.user).has_chosen)


class ProductContractTests(TestCase):
    def test_schemas_list_exactly_the_product_ids(self) -> None:
        products = set(Product.values)
        self.assertEqual(
            set(RESPONSE_SCHEMA["properties"]["product"]["enum"]) - {None}, products
        )
        self.assertEqual(set(REQUEST_SCHEMA["properties"]["product"]["enum"]), products)
        self.assertEqual(
            set(SESSION_SCHEMA["properties"]["last_product"]["enum"]) - {None}, products
        )
