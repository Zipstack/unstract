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
    key_obj = AgentKVKey(name="k", is_active=True)
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
