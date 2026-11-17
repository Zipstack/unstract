"""No worker test may build a Postgres Celery result backend.

This pins the invariant `conftest.py` sets up, because the cost of losing it is
a failure that looks like something else entirely and lands in a different
directory from its cause.

What happened: `shared/tests/test_session_lifecycle.py` does `import worker` for
two functions. `worker.py` is an entry point, so at module level it runs
`WorkerBuilder.build_celery_app(...)` -- and building an app installs it as
Celery's process-wide default. `shared_task` resolves `current_app` dynamically,
so from that moment every already-imported task reported the new app too. With
DB_* present that app carried
`result_backend='db+postgresql://...'`, and
`ide_callback/tests/test_agent_kv_callbacks.py::TestWebhookDeliveryResult` then
ran `agent_kv_finalized.apply(...).get()` against a database the unit tier has
no server for. Its `RuntimeError` assertion was masked by a
`sqlalchemy.exc.OperationalError`, or the call simply hung until the per-test
timeout. Both tests passed run alone and failed run in the lane.

The fix is `CELERY_BACKEND_DB_*` set to the EMPTY STRING in the root conftest:
empty beats the DB_* fallback because `os.getenv` returns "" for a name that is
present. Popping DB_* -- the guard that existed before -- is weaker in two ways
this file guards against someone reintroducing:

* a pop in `tests/conftest.py` only happens when `workers/tests` is collected,
  so another directory selected on its own got no protection;
* a pop is undone by anything that sets the names again, and a worker module's
  import-time `load_dotenv(<workers>/.env)` does exactly that on a developer
  machine -- with the real dev credentials.

Both assertions are here deliberately: the first fails if the env guard is
weakened, the second if the config builder stops honouring it.
"""

import os


def test_the_backend_db_env_is_present_and_empty():
    """Present-but-empty, not absent.

    Absent is the weaker state: it lets `os.getenv("CELERY_BACKEND_DB_HOST",
    os.getenv("DB_HOST", ""))` fall through to DB_*, which the root conftest
    sets and a developer's `.env` can set to something real.
    """
    for var in (
        "CELERY_BACKEND_DB_HOST",
        "CELERY_BACKEND_DB_NAME",
        "CELERY_BACKEND_DB_USER",
        "CELERY_BACKEND_DB_PASSWORD",
    ):
        assert var in os.environ, (
            f"{var} must be PRESENT and empty so it wins over the DB_* "
            "fallback; popping it hands the fallback back"
        )
        assert os.environ[var] == "", (
            f"{var}={os.environ[var]!r} -- a worker test would build a real "
            "Postgres result backend, and any app it installs becomes every "
            "later test's app"
        )


def test_a_worker_config_builds_no_result_backend():
    """The invariant that actually matters, read off the config builder.

    Asserted through `WorkerConfig` rather than by re-deriving the URL here, so
    this still fails if the fallback chain in `worker_config.py` changes shape.
    """
    from shared.infrastructure.config.worker_config import WorkerConfig

    config = WorkerConfig()

    assert config.celery_result_backend == "", (
        f"result backend is {config.celery_result_backend!r}; a Celery app "
        "built in a test would store results in a live database"
    )
