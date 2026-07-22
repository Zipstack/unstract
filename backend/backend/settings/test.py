from backend.settings.base import *  # noqa: F401, F403

DEBUG = True

# Django's default PBKDF2 hasher costs ~120ms per call; suites that seed several
# users per test spend most of their time here. Test fixtures need speed, not
# resistance to offline cracking.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
