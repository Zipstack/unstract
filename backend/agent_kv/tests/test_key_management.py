import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv.models import AgentKVKey  # noqa: E402
from agent_kv.serializers import AgentKVKeyWriteSerializer  # noqa: E402
from agent_kv.views import AgentKVKeyViewSet  # noqa: E402


def test_write_serializer_rejects_blank_name():
    s = AgentKVKeyWriteSerializer(data={"name": "", "description": "x"})
    assert not s.is_valid()
    assert "name" in s.errors


def test_rotate_assigns_fresh_key_and_saves():
    key_obj = AgentKVKey(name="k", key=uuid.uuid4())
    old = key_obj.key
    with mock.patch.object(AgentKVKey, "save") as m_save:
        view = AgentKVKeyViewSet()
        view.get_object = lambda: key_obj
        view.format_kwarg = None
        view.request = mock.Mock()
        resp = view.rotate(view.request, pk=str(key_obj.id))
    assert key_obj.key != old
    assert m_save.called
    assert resp.status_code == 200
