"""The unread count is pushed to the user's socket room when it changes."""

from importlib import import_module
from unittest.mock import call, patch

from account_v2.models import Organization
from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.test import TestCase
from permissions.tests.base import CoOwnerOrgTestMixin
from rest_framework.test import APIRequestFactory, force_authenticate
from utils import log_events
from utils.user_context import UserContext

from inbox import service
from inbox.models import InboxItem
from inbox.views import InboxViewSet

EMIT = "utils.log_events._emit_websocket_event"


def _pushed(emit, user) -> list[dict]:
    return [
        c.args[2]
        for c in emit.call_args_list
        if c.args[:2] == (f"user:{user.pk}", "inbox:unread")
    ]


class PushTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.addCleanup(UserContext.set_organization_identifier, None)

    def notify(self, users, key) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            service.notify(
                users, kind=InboxItem.Kind.RESOURCE_SHARED, title="t", dedupe_key=key
            )

    def test_new_items_push_each_recipients_count(self) -> None:
        self.notify([self.viewer], "a")
        with patch(EMIT) as emit:
            self.notify([self.viewer, self.outsider], "b")
        org = {"organization_id": "org-a"}
        self.assertEqual(_pushed(emit, self.viewer), [{**org, "unread_count": 2}])
        self.assertEqual(_pushed(emit, self.outsider), [{**org, "unread_count": 1}])

    def test_count_is_for_the_items_organization(self) -> None:
        other = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        InboxItem.objects.create(
            organization=other, user=self.viewer, kind="x", title="x", dedupe_key="o"
        )
        with patch(EMIT) as emit:
            self.notify([self.viewer], "a")
        self.assertEqual(_pushed(emit, self.viewer)[0]["unread_count"], 1)

    def test_read_and_read_all_push_the_new_count(self) -> None:
        self.notify([self.viewer], "a")
        self.notify([self.viewer], "b")
        item = InboxItem.objects.filter(user=self.viewer).first()
        factory = APIRequestFactory()

        def post(action, **kwargs):
            request = factory.post("/x/")
            force_authenticate(request, user=self.viewer)
            with self.captureOnCommitCallbacks(execute=True):
                InboxViewSet.as_view({"post": action})(request, **kwargs)

        with patch(EMIT) as emit:
            post("read", pk=str(item.pk))
            post("read_all")
        counts = [p["unread_count"] for p in _pushed(emit, self.viewer)]
        self.assertEqual(counts, [1, 0])

    def test_a_failing_push_does_not_fail_the_write(self) -> None:
        with patch(EMIT, side_effect=RuntimeError("redis down")):
            with self.assertLogs("inbox.service", "ERROR"):
                self.notify([self.viewer], "a")
        self.assertEqual(service.unread_count(self.viewer), 1)


class ConnectTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.addCleanup(UserContext.set_organization_identifier, None)
        # It would close the test's own transaction, as the test client avoids.
        patcher = patch.object(log_events, "close_old_connections")
        self.close_old = patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self, session_key: str):
        environ = {"HTTP_COOKIE": f"{settings.SESSION_COOKIE_NAME}={session_key}"}
        with patch.object(log_events.sio, "enter_room") as enter:
            log_events.connect("sid-1", environ, None)
        return enter

    def session(self, **data) -> str:
        store = import_module(settings.SESSION_ENGINE).SessionStore()
        store.update(data)
        store.create()
        return store.session_key

    def test_signed_in_socket_joins_its_users_room(self) -> None:
        key = self.session(**{SESSION_KEY: str(self.viewer.pk)})
        enter = self.connect(key)
        enter.assert_has_calls(
            [call("sid-1", key), call("sid-1", f"user:{self.viewer.pk}")]
        )

    def test_session_read_drops_stale_connections(self) -> None:
        self.connect(self.session(other="x"))
        self.assertEqual(self.close_old.call_count, 2)

    def test_anonymous_session_joins_only_the_session_room(self) -> None:
        key = self.session(other="x")
        enter = self.connect(key)
        enter.assert_called_once_with("sid-1", key)

    def test_cookie_shaped_like_a_user_room_joins_nothing(self) -> None:
        environ = {"HTTP_COOKIE": f"{settings.SESSION_COOKIE_NAME}=user:{self.viewer.pk}"}
        with (
            patch.object(log_events.sio, "enter_room") as enter,
            patch.object(log_events.sio, "disconnect") as disconnect,
        ):
            log_events.connect("sid-1", environ, None)
        enter.assert_not_called()
        disconnect.assert_called_once_with("sid-1")

    def test_failing_session_store_joins_only_the_session_room(self) -> None:
        with patch.object(log_events, "import_module", side_effect=RuntimeError("db")):
            with self.assertLogs("utils.log_events", "ERROR"):
                enter = self.connect("abc123")
        enter.assert_called_once_with("sid-1", "abc123")

    def test_unknown_session_joins_only_the_session_room(self) -> None:
        enter = self.connect("nosuchsession")
        enter.assert_called_once_with("sid-1", "nosuchsession")
