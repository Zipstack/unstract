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
from utils.filters.organization_filter import OrganizationFilterBackend  # noqa: E402


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


@mock.patch.object(AgentKVKey, "objects")
def test_org_scoping_via_filter_backend_is_engaged(m_objects):
    """Org-scoping is enforced by the global filter backend, not the manager.

    Two things must hold for that guard to stay real: (1) the viewset must
    keep ``OrganizationFilterBackend`` in its resolved ``filter_backends`` —
    so nobody can quietly swap it out later — and (2) ``get_queryset`` must
    hand back the *unscoped* base queryset (``AgentKVKey.objects.all()``,
    no ``organization=`` kwarg of its own) rather than pre-filtering, which
    would keep working (and hide the loss of protection) even if the backend
    were ever removed from ``DEFAULT_FILTER_BACKENDS``.
    """
    view = AgentKVKeyViewSet()

    assert OrganizationFilterBackend in view.filter_backends

    result = view.get_queryset()

    m_objects.all.assert_called_once_with()
    m_objects.filter.assert_not_called()
    assert result is m_objects.all.return_value


def test_create_returns_id_and_key():
    """POST .../keys/ must echo the read serializer, not the write one.

    A caller who just created a key has no other way to learn its ``id`` or
    the raw ``key`` value -- ``AgentKVKeyWriteSerializer`` (used to validate
    the request) carries neither. ``serializer.save`` is stubbed rather than
    hitting the real ORM: this file has no DB fixture, and ``ModelSerializer
    .save()``'s default create path resolves ``AgentKVKey._default_manager``
    independently of any ``mock.patch.object(AgentKVKey, "objects")`` swap
    (a different manager reference), so mocking ``.objects`` the way the
    other tests in this file do would silently fall through to a real
    database call here.
    """
    key_obj = AgentKVKey(
        id=uuid.uuid4(), name="k", description="", key=uuid.uuid4(), is_active=True
    )

    def _fake_save(self, **kwargs):
        self.instance = key_obj
        return key_obj

    view = AgentKVKeyViewSet()
    view.action = "create"
    view.format_kwarg = None
    view.kwargs = {}
    view.request = mock.Mock(data={"name": "k"}, user=mock.Mock())

    with mock.patch.object(AgentKVKeyWriteSerializer, "save", _fake_save):
        resp = view.create(view.request)

    assert resp.status_code == 201, resp.data
    # DRF serializes UUID fields as strings.
    assert resp.data["id"] == str(key_obj.id), resp.data
    assert resp.data["key"] == str(key_obj.key), resp.data
