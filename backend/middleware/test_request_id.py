"""Request-level tests for ``X-Request-ID`` provisioning at the HTTP boundary.

Two properties are pinned here, and they pull in opposite directions.

*The id is server-provisioned.* A caller-supplied id is ignored on public
routes. Honouring one would let a client send the same value on every request,
and a log query for it would then return unrelated requests across tenants --
which reads as though correlation worked. The id also reaches every log line and
every published Celery message, so an unvalidated one can forge a log record.

*Except across the internal boundary,* where the caller is our own worker
forwarding the id of the request that started the execution. That hop is what
makes worker logs correlate back to the originating call, and it hinges on a
single setting with a silent failure mode: when ``LOG_REQUEST_ID_HEADER`` is the
raw header name rather than the WSGI ``META`` key, ``django-log-request-id``
looks up a key that never exists and mints a fresh id instead. Nothing errors --
every service just logs a different id. Settings are deliberately *not*
overridden here, so reverting the production value fails these tests.

No DB is touched (``SimpleTestCase`` + a bare middleware list), keeping this in
the fast unit tier.
"""

import re
import uuid

from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings
from django.urls import path

# Set by CustomRequestIDMiddleware; echoed back so the view can assert on it.
REQUEST_ID_ECHO_HEADER = "X-Seen-Request-Id"


def _echo_view(request):
    """Reports the request id the middleware bound, so the test can compare it
    against both the id sent in and the id echoed on the response.
    """
    response = HttpResponse("ok")
    response[REQUEST_ID_ECHO_HEADER] = getattr(request, "id", "<unset>")
    return response


PUBLIC_URL = "/echo/"
INTERNAL_URL = "/internal/echo/"

urlpatterns = [
    path("echo/", _echo_view),
    path("internal/echo/", _echo_view),
]

# Just the middleware under test: no auth, tenancy or session, so nothing here
# reaches the database.
_MIDDLEWARE = ["middleware.request_id.CustomRequestIDMiddleware"]

_UUID4_RE = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class PublicRequestIDTest(SimpleTestCase):
    """Public routes: the id is ours, whatever the caller sent."""

    def test_caller_supplied_id_is_ignored(self):
        """The frontend attaches a uuid4 of its own to every call. It is still
        the backend's id that is authoritative -- the frontend reads the value
        back off the response header, so nothing is lost by ignoring it.
        """
        sent = "11111111-2222-4333-8444-555555555555"

        response = self.client.get(PUBLIC_URL, headers={"x-request-id": sent})

        bound = response[REQUEST_ID_ECHO_HEADER]
        self.assertNotEqual(bound, sent)
        self.assertRegex(bound, _UUID4_RE)

    def test_repeated_caller_id_does_not_collapse_requests(self):
        """The reason a caller's id is not adopted: one repeated across requests
        would make a single log query return unrelated requests, and read as
        though it had worked.
        """
        sent = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        headers = {"x-request-id": sent}

        first = self.client.get(PUBLIC_URL, headers=headers)
        second = self.client.get(PUBLIC_URL, headers=headers)

        self.assertNotEqual(first[REQUEST_ID_ECHO_HEADER], second[REQUEST_ID_ECHO_HEADER])

    def test_hostile_id_never_reaches_a_log_line(self):
        """An id lands unescaped in every log line, so one carrying terminal
        control codes could erase the real prefix of a record and forge the
        rest. gunicorn rejects only NUL/CR/LF, so the escape arrives intact.
        """
        sent = "\x1b[2K\x1b[1000Ddeadbeef} :- SPOOFED: admin deleted org 42"

        response = self.client.get(PUBLIC_URL, headers={"x-request-id": sent})

        self.assertRegex(response[REQUEST_ID_ECHO_HEADER], _UUID4_RE)

    def test_response_echoes_the_provisioned_id(self):
        """The response carries the id back, which is how the frontend surfaces
        it on an error and how anyone debugging a live call retrieves it.
        """
        response = self.client.get(PUBLIC_URL)

        echoed = response["X-Request-ID"]
        self.assertRegex(echoed, _UUID4_RE)
        self.assertEqual(response[REQUEST_ID_ECHO_HEADER], echoed)

    def test_distinct_callers_get_distinct_ids(self):
        """Two requests must not share an id, or correlation collapses instead
        of merely missing.
        """
        first = self.client.get(PUBLIC_URL)["X-Request-ID"]
        second = self.client.get(PUBLIC_URL)["X-Request-ID"]

        self.assertNotEqual(first, second)

    def test_uuid_module_still_backs_the_generator(self):
        """Guards the custom ``_generate_id`` override, which exists so ids are
        plain uuid4 strings rather than the library's default hex form.
        """
        response = self.client.get(PUBLIC_URL)

        parsed = uuid.UUID(response["X-Request-ID"])
        self.assertEqual(str(parsed), response["X-Request-ID"])


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class InternalRequestIDTest(SimpleTestCase):
    """The internal boundary: a worker's forwarded id is honoured."""

    def test_forwarded_id_is_adopted(self):
        """The hop that silently broke: workers send the originating request's
        id on their callbacks, and before the fix the backend discarded it.
        """
        sent = "11111111-2222-4333-8444-555555555555"

        response = self.client.get(INTERNAL_URL, headers={"x-request-id": sent})

        self.assertEqual(
            response[REQUEST_ID_ECHO_HEADER],
            sent,
            "backend minted a new id instead of adopting the worker's -- "
            "LOG_REQUEST_ID_HEADER must be the WSGI META key HTTP_X_REQUEST_ID, "
            "not the raw header name",
        )
        self.assertEqual(response["X-Request-ID"], sent)

    def test_forwarded_id_must_be_a_uuid(self):
        """The boundary is authenticated downstream, not here, so an unauthorised
        caller can still reach this path. Only the shape our own services emit is
        accepted, which bounds both length and character set.
        """
        response = self.client.get(INTERNAL_URL, headers={"x-request-id": "edge-lb-7f"})

        self.assertRegex(response[REQUEST_ID_ECHO_HEADER], _UUID4_RE)

    def test_overlong_forwarded_id_is_rejected(self):
        """An id is re-stamped onto every published Celery message and every log
        line of an execution, so an unbounded one amplifies: gunicorn accepts
        ~8KB, which one call can fan out across N file tasks.
        """
        response = self.client.get(INTERNAL_URL, headers={"x-request-id": "A" * 8000})

        self.assertRegex(response[REQUEST_ID_ECHO_HEADER], _UUID4_RE)

    def test_id_is_provisioned_when_nothing_is_forwarded(self):
        response = self.client.get(INTERNAL_URL)

        self.assertRegex(response[REQUEST_ID_ECHO_HEADER], _UUID4_RE)


@override_settings(
    ROOT_URLCONF=__name__,
    MIDDLEWARE=["corsheaders.middleware.CorsMiddleware"] + _MIDDLEWARE,
)
class RequestIDIsReadableByTheBrowserTest(SimpleTestCase):
    """The frontend is a separate origin, so the echo only reaches JS if the
    header is named in ``CORS_EXPOSE_HEADERS``.

    Without it the browser hides the header, ``getRequestIdFromError`` falls
    through to the id the interceptor *sent*, and -- now that the backend
    provisions its own -- the error toast shows an id that appears in no log.
    Nothing errors; the id is simply wrong, which is why this is pinned.
    """

    def test_request_id_is_exposed_to_a_cross_origin_caller(self):
        origin = "http://localhost:3000"

        response = self.client.get(
            PUBLIC_URL, headers={"origin": origin, "x-request-id": "ignored"}
        )

        exposed = response.get("Access-Control-Expose-Headers", "")
        self.assertIn(
            "X-Request-ID",
            [h.strip() for h in exposed.split(",")],
            "the browser cannot read the id the backend logged",
        )
        self.assertRegex(response["X-Request-ID"], _UUID4_RE)
