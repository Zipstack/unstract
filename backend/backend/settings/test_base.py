"""Test-only setting deltas, shared by the OSS and cloud test settings.

This module imports nothing on purpose. `copy_cloud_deps` replaces the OSS
`settings/test.py` on a cloud build, so a delta that lives only in that file is
silently lost there; keeping the deltas here is what stops the two trees
diverging. Star-importing a base settings module would re-export its names and
clobber whatever the importer derived from `cloud`, so this file defines only
what it overrides.
"""

DEBUG = True

# Django's default PBKDF2 hasher is deliberately slow; suites that seed several
# users per test spend most of their time there. Test fixtures need speed, not
# resistance to offline cracking.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Prod enforces HTTPS-only cookies; tests run over plain HTTP.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Env-driven and unset under test, which would make any request to an internal
# API fail as "not configured" rather than on its own merits.
INTERNAL_SERVICE_API_KEY = "test-internal-service-key"

# The organization-scoped MCP server ships disabled (see
# MCP_PLATFORM_SERVER_ENABLED in base.py), but its tests must still exercise
# it: several drive requests through the full URL stack precisely so the auth
# middleware runs, and an unmounted route would make them 404 — turning a suite
# that checks a credential is *rejected* into one that passes because nothing
# is there. Shipping-off and untested are different things.
MCP_PLATFORM_SERVER_ENABLED = True
