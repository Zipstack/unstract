from backend.settings.base import *  # noqa: F401, F403

DEBUG = True

# Django's default PBKDF2 hasher is deliberately slow; suites that seed several
# users per test spend most of their time there. Test fixtures need speed, not
# resistance to offline cracking.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The organization-scoped MCP server ships disabled (see
# MCP_PLATFORM_SERVER_ENABLED in base.py), but its tests must still exercise
# it: several drive requests through the full URL stack precisely so the auth
# middleware runs, and an unmounted route would make them 404 — turning a suite
# that checks a credential is *rejected* into one that passes because nothing
# is there. Shipping-off and untested are different things.
MCP_PLATFORM_SERVER_ENABLED = True
