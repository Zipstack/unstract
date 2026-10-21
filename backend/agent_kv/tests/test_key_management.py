import os
import uuid
from unittest import mock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from utils.filters.organization_filter import OrganizationFilterBackend  # noqa: E402

from agent_kv.models import AgentKVKey  # noqa: E402
from agent_kv.serializers import (  # noqa: E402
    AgentKVKeyCreateSerializer,
    AgentKVKeyDetailSerializer,
    AgentKVKeyListSerializer,
    AgentKVKeyUpdateSerializer,
)
from agent_kv.views import AgentKVKeyViewSet  # noqa: E402


def test_create_serializer_rejects_blank_name():
    s = AgentKVKeyCreateSerializer(data={"name": "", "description": "x"})
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
    the raw ``key`` value -- ``AgentKVKeyCreateSerializer`` (used to validate
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
    view.request = mock.Mock(
        data={"name": "k", "description": "d"}, user=mock.Mock()
    )

    # `validate_name` checks the per-org name uniqueness the model constrains,
    # which is a real query; both halves of it are stubbed because this file
    # has no database. Mocking `.objects` is safe HERE and nowhere else in
    # this test — see the note above about `save()` resolving
    # `_default_manager` instead — because `save` is stubbed too.
    with mock.patch.object(AgentKVKeyCreateSerializer, "save", _fake_save):
        with mock.patch("agent_kv.serializers.UserContext.get_organization"):
            with mock.patch.object(AgentKVKey, "objects") as m_objects:
                m_objects.filter.return_value.exists.return_value = False
                resp = view.create(view.request)

    assert resp.status_code == 201, resp.data
    # DRF serializes UUID fields as strings.
    assert resp.data["id"] == str(key_obj.id), resp.data
    assert resp.data["key"] == str(key_obj.key), resp.data


# ---------------------------------------------------------------------------
# What each response is allowed to show.
# ---------------------------------------------------------------------------
#
# The keys page lists every key in the organization in one table. Returning the
# real value there would put the whole set on screen to read one of them, so
# list MASKS and only the three single-key responses (create, rotate, an
# explicit retrieve behind the copy button) carry the plaintext. This mirrors
# `platform_api`, which settled the same question first; the single serializer
# this replaced returned the real key everywhere, which was survivable only
# while nothing called the endpoint.


def _key(**kwargs):
    kwargs.setdefault("key", uuid.UUID("3f2504e0-4f89-41d3-9a0c-0305e82c3301"))
    kwargs.setdefault("name", "k")
    kwargs.setdefault("description", "d")
    return AgentKVKey(id=uuid.uuid4(), is_active=True, **kwargs)


def test_the_list_never_carries_a_usable_key():
    key_obj = _key()

    data = AgentKVKeyListSerializer(key_obj).data

    assert data["key"] == "****-3301"
    assert str(key_obj.key) not in data["key"]


def test_the_detail_response_carries_the_real_key():
    """Create, rotate and copy are each a request for ONE key the caller
    already has a reason to hold. A masked value here would leave the copy
    button with nothing to copy.
    """
    key_obj = _key()

    data = AgentKVKeyDetailSerializer(key_obj).data

    assert data["key"] == str(key_obj.key)


def test_a_key_whose_creator_was_deleted_still_names_a_creator():
    """`created_by` is `on_delete=SET_NULL`, so a key outlives the admin who
    made it. An empty cell in the table reads as a bug rather than as history.
    """
    assert AgentKVKeyListSerializer(_key()).data["created_by_email"] == "Deleted user"


def test_each_action_gets_the_serializer_that_matches_its_exposure():
    """The routing itself, since every assertion above tests a serializer in
    isolation and would still pass if the viewset picked the wrong one.
    """
    view = AgentKVKeyViewSet()
    expected = {
        "list": AgentKVKeyListSerializer,
        "retrieve": AgentKVKeyDetailSerializer,
        "rotate": AgentKVKeyDetailSerializer,
        "create": AgentKVKeyCreateSerializer,
        "partial_update": AgentKVKeyUpdateSerializer,
    }

    for action, serializer in expected.items():
        view.action = action
        assert view.get_serializer_class() is serializer, action


def test_rotate_returns_the_new_key_in_full():
    """The point of rotating is to receive the replacement; a masked response
    would make the action useless.
    """
    key_obj = _key()
    old = key_obj.key
    with mock.patch.object(AgentKVKey, "save"):
        view = AgentKVKeyViewSet()
        view.get_object = lambda: key_obj
        view.format_kwarg = None
        view.request = mock.Mock()
        resp = view.rotate(view.request, pk=str(key_obj.id))

    assert resp.data["key"] == str(key_obj.key)
    assert resp.data["key"] != str(old)
