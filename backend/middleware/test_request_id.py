"""Request-level tests for ``X-Request-ID`` correlation at the HTTP boundary.

The correlation chain this PR builds (backend -> Celery workers -> internal API
callbacks) is only anchored if the backend actually *adopts* the id its caller
sent. That hinges on a single setting, and the failure mode is silent: when
``LOG_REQUEST_ID_HEADER`` is the raw header name rather than the WSGI ``META``
key, ``django-log-request-id`` looks up a key that never exists, falls through
to ``GENERATE_REQUEST_ID_IF_NOT_IN_HEADER`` and mints a fresh uuid4 per
request. Nothing errors -- every service just logs a different id, and the
single-``request_id`` log query the feature exists for returns one hop.

So these assert the contract end-to-end through a real middleware chain rather
than asserting on the setting's value: send a header, get the same id back.
Settings are deliberately *not* overridden here -- ``backend.settings.test``
re-exports ``base``, so reverting the production value fails these tests.

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


urlpatterns = [path("echo/", _echo_view)]
ECHO_URL = "/echo/"

# Just the middleware under test: no auth, tenancy or session, so nothing here
# reaches the database.
_MIDDLEWARE = ["middleware.request_id.CustomRequestIDMiddleware"]

_UUID4_RE = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=_MIDDLEWARE)
class IncomingRequestIDTest(SimpleTestCase):
    def test_incoming_header_is_adopted_as_request_id(self):
        """The id a caller sends becomes ``request.id`` verbatim.

        This is the hop that silently broke: the frontend and the workers both
        send ``X-Request-ID``, and before the fix the backend discarded it.
        """
        sent = "11111111-2222-4333-8444-555555555555"

        response = self.client.get(ECHO_URL, headers={"x-request-id": sent})

        self.assertEqual(
            response[REQUEST_ID_ECHO_HEADER],
            sent,
            "backend minted a new id instead of adopting the caller's -- "
            "LOG_REQUEST_ID_HEADER must be the WSGI META key HTTP_X_REQUEST_ID, "
            "not the raw header name",
        )

    def test_response_echoes_the_incoming_id(self):
        """The response carries the same id back, which is how the frontend and
        anyone debugging a live call retrieve it.
        """
        sent = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

        response = self.client.get(ECHO_URL, headers={"x-request-id": sent})

        self.assertEqual(response["X-Request-ID"], sent)

    def test_id_is_minted_and_echoed_when_header_absent(self):
        """With no incoming header the backend still assigns an id and returns
        it, so a caller that sends nothing can still correlate afterwards.
        """
        response = self.client.get(ECHO_URL)

        minted = response["X-Request-ID"]
        self.assertRegex(minted, _UUID4_RE)
        self.assertEqual(response[REQUEST_ID_ECHO_HEADER], minted)

    def test_distinct_callers_get_distinct_ids(self):
        """Two header-less requests must not share an id, or correlation
        collapses instead of merely missing.
        """
        first = self.client.get(ECHO_URL)["X-Request-ID"]
        second = self.client.get(ECHO_URL)["X-Request-ID"]

        self.assertNotEqual(first, second)

    def test_non_uuid_incoming_id_is_preserved(self):
        """Ids are opaque: an upstream proxy's own format is adopted as-is
        rather than being normalised or replaced.
        """
        sent = "edge-lb-7f3a91"

        response = self.client.get(ECHO_URL, headers={"x-request-id": sent})

        self.assertEqual(response[REQUEST_ID_ECHO_HEADER], sent)
        self.assertEqual(response["X-Request-ID"], sent)

    def test_uuid_module_still_backs_the_generator(self):
        """Guards the custom ``_generate_id`` override, which exists so ids are
        plain uuid4 strings rather than the library's default hex form.
        """
        response = self.client.get(ECHO_URL)

        # Parses without raising, and round-trips to the same string.
        parsed = uuid.UUID(response["X-Request-ID"])
        self.assertEqual(str(parsed), response["X-Request-ID"])
