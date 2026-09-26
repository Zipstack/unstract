# ADR-014: Internal and external APIs separated per app

## Context

Workers and other backend services need to call the Django backend, but they must not authenticate the way an end user does, and the surface they need is narrower and shaped differently from the public REST API. Mixing the two surfaces in the same view module is the path to accidental privilege escalation: a public-facing decorator change can silently affect a service-to-service endpoint.

## Decision

Each Django app that exposes a service-to-service surface keeps it in separate files:

- `urls.py` and `views.py` for the external (end-user) surface.
- `internal_urls.py` and `internal_views.py` for the service-to-service surface.

The internal surface is mounted under a distinct URL prefix and is protected by `InternalAPIAuthMiddleware`. End-user auth middleware does not run on internal endpoints, and vice versa.

## Consequences

- Changing one surface cannot accidentally change the other.
- Workers call backend functionality via the internal client (see `workers/shared/api_client.py`) using the internal surface only.
- New service-to-service needs land in `internal_views.py`, not in the public REST viewset.
