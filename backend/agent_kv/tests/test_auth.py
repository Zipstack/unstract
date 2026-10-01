import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

import pytest  # noqa: E402
from api_v2.exceptions import Forbidden  # noqa: E402
from agent_kv.key_validator import AgentKVKeyValidator  # noqa: E402
from agent_kv.models import AgentKVKey  # noqa: E402


def _request(auth=None):
    r = mock.Mock()
    r.headers = {"Authorization": auth} if auth else {}
    return r


def _wrapped():
    @AgentKVKeyValidator.validate_api_key
    def view(self, request, *args, **kwargs):
        return kwargs["agent_kv_key"]
    return view


def test_missing_key_is_forbidden():
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request())


@mock.patch.object(AgentKVKey, "objects")
def test_unknown_key_is_forbidden(m_objects):
    m_objects.get.side_effect = AgentKVKey.DoesNotExist
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request(f"Bearer {uuid.uuid4()}"))


@mock.patch.object(AgentKVKey, "objects")
def test_valid_key_injected_into_kwargs(m_objects):
    from account_v2.models import Organization  # noqa: PLC0415

    key_obj = AgentKVKey(name="k", is_active=True)
    # A usable key always has an organization: every downstream use is
    # org-scoped, and the validator refuses one without (see the org-less test
    # at the bottom of this module).
    key_obj.organization = Organization(id=1, organization_id="acme-slug")
    m_objects.get.return_value = key_obj
    out = _wrapped()(mock.Mock(), _request(f"Bearer {uuid.uuid4()}"))
    assert out is key_obj


@mock.patch.object(AgentKVKey, "objects")
def test_non_uuid_key_is_forbidden_without_db_hit(m_objects):
    with pytest.raises(Forbidden):
        _wrapped()(mock.Mock(), _request("Bearer not-a-uuid"))
    assert not m_objects.get.called


def test_prefix_is_whitelisted():
    from django.conf import settings
    assert f"/{settings.AGENT_KV_PATH_PREFIX}" in settings.WHITELISTED_PATHS


def test_public_url_wiring_and_decorator_enforced():
    """Regression pin for the two failure modes the decorator-only tests above
    can't catch (they exercise the hand-built `_wrapped()` helper, not the
    real view or URLconf):

    (a) dropping `include("agent_kv.execution_urls")` from base_urls.py, and
    (b) dropping `@AgentKVKeyValidator.validate_api_key` from SubmitView.post.

    This drives the real URL resolution and class-based view dispatch path
    instead: (a) breaks `resolve(...)`, and (b) makes the stub answer with
    501 for every request instead of 403 for an unauthenticated one.
    """
    from django.conf import settings
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory

    from agent_kv.execution_views import SubmitView

    resolved = resolve(f"/{settings.AGENT_KV_PATH_PREFIX}/")
    assert resolved.func.cls is SubmitView

    request = APIRequestFactory().post(f"/{settings.AGENT_KV_PATH_PREFIX}/")
    response = SubmitView.as_view()(request)
    assert response.status_code == 403


def test_key_without_an_organization_is_refused():
    """`organization` is nullable on AgentKVKey, but every downstream use of a
    key is org-scoped -- the subscription gate, the concurrency limiter, the
    storage prefix, every job lookup. Before this guard the first of those to
    touch `key.organization` raised AttributeError and the caller got a 500;
    found by running a real submit against a stack whose key had no org.
    """
    from unittest import mock  # noqa: PLC0415

    from api_v2.exceptions import Forbidden  # noqa: PLC0415

    from agent_kv.key_validator import AgentKVKeyValidator  # noqa: PLC0415
    from agent_kv.models import AgentKVKey  # noqa: PLC0415

    orgless = AgentKVKey(name="k", is_active=True)
    assert orgless.organization_id is None
    with mock.patch.object(AgentKVKey, "objects") as m_objects:
        m_objects.get.return_value = orgless
        try:
            AgentKVKeyValidator.validate_and_process(
                object(), object(), lambda *a, **k: "reached the view",
                "123e4567-e89b-12d3-a456-426614174001",
            )
        except Forbidden:
            pass
        else:
            raise AssertionError("an org-less key must not reach the view")
