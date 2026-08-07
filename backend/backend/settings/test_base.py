"""Test-only setting deltas, shared by the OSS and cloud test settings.

Imports nothing on purpose: `copy_cloud_deps` replaces the OSS `settings/test.py`
on a cloud build, so deltas kept only there are lost, and star-importing a base
module here would re-export its names over whatever the importer derived.
"""

DEBUG = True

# PBKDF2 is deliberately slow, and suites seeding users per test pay it repeatedly.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Prod enforces HTTPS-only cookies; tests run over plain HTTP.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Env-driven, so unset under test: without it internal-API requests fail as
# "not configured" rather than on their own merits.
INTERNAL_SERVICE_API_KEY = "test-internal-service-key"

# Ships disabled, but its tests drive the full URL stack to exercise the auth
# middleware — an unmounted route would 404 and pass them vacuously.
MCP_PLATFORM_SERVER_ENABLED = True
