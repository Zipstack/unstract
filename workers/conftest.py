"""Root conftest for workers test suite.

Sets required environment variables before any workers modules are imported,
and makes it impossible for a worker test to build a Postgres Celery result
backend.
"""

import os

# These must be set before any workers module import because
# shared/constants/api_endpoints.py evaluates INTERNAL_API_BASE_URL at class definition time.
os.environ.setdefault("INTERNAL_API_BASE_URL", "http://test-backend:8000/internal")
os.environ.setdefault("INTERNAL_SERVICE_API_KEY", "test-key-123")
os.environ.setdefault("CELERY_BROKER_BASE_URL", "amqp://localhost:5672//")
os.environ.setdefault("CELERY_BROKER_USER", "guest")
os.environ.setdefault("CELERY_BROKER_PASS", "guest")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "testdb")

# NO WORKER TEST MAY BUILD A POSTGRES CELERY RESULT BACKEND.
#
# `WorkerConfig` builds `celery_result_backend` as
# `db+postgresql://{user}:{pw}@{host}:{port}/{name}` whenever host, user,
# password and name are all non-empty, and each falls back to the DB_* above:
# `os.getenv("CELERY_BACKEND_DB_HOST", os.getenv("DB_HOST", ""))`. Building a
# Celery app also INSTALLS it as the process-wide default, and `shared_task`
# resolves `current_app` dynamically -- so one test importing an entry point
# (`import worker` runs `WorkerBuilder.build_celery_app` at module level) gives
# every later test a task bound to an app whose results live in a database the
# unit tier has no server for. `.apply().get()` then reaches for it.
#
# Set EXPLICITLY EMPTY rather than popped, and that is the whole point:
# `os.getenv` returns "" for a name that is present-but-empty, so this WINS
# over the DB_* fallback instead of deferring to it. Popping DB_* cannot do the
# same job, because a pop only holds until something puts them back -- and
# something does. `tests/conftest.py` pops them, and on a developer machine a
# worker module's own import-time `load_dotenv(<workers>/.env)` then
# re-introduces the REAL dev credentials, which is how a unit test came to
# authenticate against `unstract-db` as `unstract_dev`. An empty value here
# survives that, because the fallback is never consulted.
#
# In the ROOT conftest so it holds for every worker test directory, whichever
# subset is selected. The pop in `tests/conftest.py` was the only guard before
# and could never be enough: it loads when `workers/tests` is collected, so
# running `shared/tests ide_callback/tests` on their own had no protection at
# all. `shared/tests/test_no_pg_result_backend.py` pins this.
for _backend_var in (
    "CELERY_BACKEND_DB_HOST",
    "CELERY_BACKEND_DB_NAME",
    "CELERY_BACKEND_DB_USER",
    "CELERY_BACKEND_DB_PASSWORD",
):
    os.environ[_backend_var] = ""
# Keep image-limits lookups on the bundled table (no fetch from GitHub).
os.environ.setdefault("VLM_IMAGE_LIMITS_URL", "")
