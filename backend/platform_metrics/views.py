"""``GET /metrics``: platform metrics in Prometheus text format (UN-4251).

Mounted at the URL root, beside ``/health``, which keeps it off the public
ingress: that sends the backend only prefixed paths (``/api/v1``,
``/deployment``, ``/public``, ...) and everything else to the frontend, so
``/metrics`` is reachable only in-cluster, on the backend service.
The data is platform-wide, so it is also exempt from session auth
(``WHITELISTED_PATHS``) and guarded instead by an optional bearer token,
``PLATFORM_METRICS_TOKEN``, for environments that want one.

``?group=<name>`` (repeatable) limits the scrape to those metric groups, e.g.
``?group=queues`` for an autoscaler that only needs queue depth.

A plain Django view rather than DRF: the response is the exposition bytes as
they are, with no content negotiation or renderer in between.
"""

import hmac

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET

from .exporter import UnknownGroup, get_exporter

_BEARER = "Bearer "
# The text format generate_latest() writes, spelled out rather than taken from
# prometheus_client's CONTENT_TYPE_LATEST, which newer releases point at the
# 1.0.0 format that older scrapers do not recognise. Matches the PG workers'
# /metrics (workers/queue_backend/pg_queue/metrics.py).
METRICS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _authorised(request: HttpRequest) -> bool:
    token = settings.PLATFORM_METRICS_TOKEN
    if not token:
        return True
    header = request.headers.get("Authorization", "")
    if not header.startswith(_BEARER):
        return False
    return hmac.compare_digest(header[len(_BEARER) :].encode(), token.encode())


# Non-atomic so each group's refresh is its own outermost transaction even with
# ATOMIC_REQUESTS on: its SET LOCAL statement_timeout then ends with it.
@transaction.non_atomic_requests
@require_GET
def metrics(request: HttpRequest) -> HttpResponse:
    if not _authorised(request):
        response = HttpResponse("Unauthorized\n", status=401, content_type="text/plain")
        response["WWW-Authenticate"] = 'Bearer realm="metrics"'
        return response
    # ?group=queues (repeatable) serves only those groups, so a reader that
    # needs one never waits on another group's refresh.
    try:
        body = get_exporter().render(request.GET.getlist("group") or None)
    except UnknownGroup as e:
        return HttpResponse(
            f"Unknown metric group: {e}\n", status=400, content_type="text/plain"
        )
    return HttpResponse(body, content_type=METRICS_CONTENT_TYPE)
