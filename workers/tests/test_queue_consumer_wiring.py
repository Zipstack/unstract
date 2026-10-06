"""Guard: every queue we dispatch to must have a consumer in the deployed fleet.

This is the OSS analogue of the cloud chart's ``validate-pg-worker-fleet.yaml``.
It exists because the failure it catches is **silent**: since UN-4046 made the
PG transport unconditional, a queue whose consumer is not configured still
*accepts* work -- ``enqueue_task`` succeeds, rows land in ``pg_queue_message``,
and nothing errors at the producer. The job simply sits in DISPATCHED forever.

That is exactly what happened to ``celery_executor_agentic_kv``: the Agent-KV
branch was written when the Celery executor was live, so its queue was wired
into ``CELERY_QUEUES_EXECUTOR`` -- a variable read only by
``workers/executor/worker.py`` (the now-disabled Celery worker). The live
``pg-queue-consumer`` reads ``WORKER_PG_QUEUE_CONSUMER_QUEUE``, which did not
list it.

Each test therefore asserts the queue is present in the variable the *running*
consumer actually reads, at every site that configures one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yaml"
TEST_COMPOSE = REPO_ROOT / "tests" / "compose" / "docker-compose.test.yaml"
RUN_WORKER = REPO_ROOT / "workers" / "run-worker.sh"

# The queue the `kv` extractor WOULD dispatch onto, and which this deployment
# deliberately does not serve: the `agentic_kv` plugin ships on a separate PR.
# `kv` is absent from EXTRACTOR_ROUTES so a submit is refused at the serializer
# with a 400 -- these assertions are the second half of that, pinning that no
# fleet advertises a consumer for it. A queue that is listed but unserved
# accepts work and drains nothing, with no error at the producer: the job sits
# in DISPATCHED forever. That failure has already cost this team ~30 hours of
# firings with zero executions, which is why it is guarded from both ends.
UNSERVED_KV_QUEUE = "celery_executor_agentic_kv"

# The terminal-callback queue. Its consumer is what moves a job out of
# RUNNING: finalize persists the result, deletes the staged input, releases
# the concurrency slot and fires the webhook.
AGENT_KV_CALLBACK_QUEUE = "agent_kv_callback"

# The queue the backend dispatches Agent-KV TABLE extraction onto. Same queue
# the IDE table path already uses -- ExecutionContext(executor_name=
# "agentic_table") -> celery_executor_agentic_table -- which is exactly why the
# API path reuses that executor name rather than introducing one of its own.
# It was already wired for the IDE; these assertions keep it wired now that a
# second, paid entry point depends on it.
AGENT_TABLE_QUEUE = "celery_executor_agentic_table"

# The env var the live PG consumer reads. Named here so a future rename has to
# touch this constant rather than silently bypassing every assertion below.
PG_QUEUE_VAR = "WORKER_PG_QUEUE_CONSUMER_QUEUE"

# Read only by the disabled Celery executor. Setting a queue here does NOT give
# it a consumer -- asserting its absence is what makes this suite catch the
# original bug rather than a cosmetic rename of it.
DEAD_CELERY_VAR = "CELERY_QUEUES_EXECUTOR"


def _service_env(compose_path: Path, service: str) -> dict[str, str]:
    """Return ``service``'s environment as a dict, from a compose file."""
    doc = yaml.safe_load(compose_path.read_text())
    env = (doc.get("services", {}).get(service) or {}).get("environment") or []
    if isinstance(env, dict):  # mapping form
        return {k: str(v) for k, v in env.items()}
    out: dict[str, str] = {}
    for item in env:  # list form: "KEY=value"
        key, _, value = str(item).partition("=")
        out[key] = value
    return out


def _queues(raw: str) -> set[str]:
    """Queue names from a consumer queue list, ignoring any ``${VAR:-default}``
    wrapper the compose file uses to keep the value overridable.
    """
    inner = re.sub(r"^\$\{[^:}]+:-(.*)\}$", r"\1", raw.strip())
    return {q.strip() for q in inner.split(",") if q.strip()}


@pytest.mark.parametrize(
    ("compose_path", "label"),
    [(DEV_COMPOSE, "dev compose"), (TEST_COMPOSE, "e2e test compose")],
)
def test_no_fleet_advertises_the_unserved_kv_queue(compose_path, label):
    """The executor fleet must not list a queue with no plugin behind it."""
    env = _service_env(compose_path, "worker-pg-executor")
    raw = env.get(PG_QUEUE_VAR)
    assert raw is not None, (
        f"{label}: worker-pg-executor sets no {PG_QUEUE_VAR}; the running "
        f"pg-queue-consumer would fall back to a default of unknown content"
    )
    assert UNSERVED_KV_QUEUE not in _queues(raw), (
        f"{label}: {UNSERVED_KV_QUEUE} is advertised but this deployment "
        f"carries no agentic_kv plugin to drain it. Work routed there is "
        f"accepted and never runs, silently. Remove it from {PG_QUEUE_VAR}, "
        f"or ship the plugin."
    )


def test_test_compose_does_not_wire_the_queue_onto_the_dead_celery_var():
    """Regression: the e2e override once set the Celery-only variable.

    That drained nothing on the PG transport. If someone re-adds it, the queue
    looks configured while the lane still hangs -- so fail loudly.
    """
    env = _service_env(TEST_COMPOSE, "worker-pg-executor")
    assert DEAD_CELERY_VAR not in env, (
        f"{DEAD_CELERY_VAR} is read only by the disabled Celery executor "
        f"(workers/executor/worker.py). Queues belong in {PG_QUEUE_VAR}."
    )


def test_run_worker_pg_executor_role_omits_the_unserved_kv_queue():
    """The host-run fleet's hardcoded role default must match the compose stacks.

    ``run-worker.sh`` carries its own PG_CONSUMER_ROLES map; a queue listed
    here but not in compose is just as unconsumed for anyone running the fleet
    directly.
    """
    text = RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_EXECUTOR"\]="executor;([^"]+)"', text)
    assert match, "could not find the PG_ROLE_EXECUTOR entry in run-worker.sh"
    assert UNSERVED_KV_QUEUE not in _queues(match.group(1)), (
        f"run-worker.sh's pg-executor role advertises {UNSERVED_KV_QUEUE}; a "
        f"host-run fleet would accept Agent-KV work and never drain it."
    )


@pytest.mark.parametrize(
    ("compose_path", "label"),
    [(DEV_COMPOSE, "dev compose"), (TEST_COMPOSE, "e2e test compose")],
)
def test_pg_executor_consumes_the_agent_table_queue(compose_path, label):
    """Agent-KV table jobs ride the IDE table executor's queue (spec R1)."""
    env = _service_env(compose_path, "worker-pg-executor")
    raw = env.get(PG_QUEUE_VAR)
    assert raw is not None, (
        f"{label}: worker-pg-executor sets no {PG_QUEUE_VAR}; the running "
        f"pg-queue-consumer would fall back to a default that omits "
        f"{AGENT_TABLE_QUEUE}"
    )
    assert AGENT_TABLE_QUEUE in _queues(raw), (
        f"{label}: {AGENT_TABLE_QUEUE} has no consumer -- both IDE table "
        f"prompts and Agent-KV table jobs will sit in DISPATCHED forever with "
        f"no error at the producer. Add it to {PG_QUEUE_VAR}."
    )


def test_run_worker_pg_executor_role_lists_the_agent_table_queue():
    text = RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_EXECUTOR"\]="executor;([^"]+)"', text)
    assert match, "could not find the PG_ROLE_EXECUTOR entry in run-worker.sh"
    assert AGENT_TABLE_QUEUE in _queues(match.group(1)), (
        f"run-worker.sh's pg-executor role omits {AGENT_TABLE_QUEUE}; a "
        f"host-run fleet would accept table work and never drain it."
    )


def test_pg_ide_callback_drains_the_agent_kv_callback_queue():
    """Without this the job runs to SUCCESS and then never completes.

    The executor enqueues its terminal continuation onto `agent_kv_callback`;
    if no consumer drains it the row sits in pg_queue_message and the job stays
    RUNNING forever, with nothing logged at the producer. The Celery
    ide_callback worker has carried both queues since the callbacks landed --
    its PG twin did not, and the cloud chart wires it correctly, so only the
    OSS stacks were affected. Found by running a real job end to end.
    """
    env = _service_env(DEV_COMPOSE, "worker-pg-ide-callback")
    raw = env.get(PG_QUEUE_VAR)
    assert raw is not None, "worker-pg-ide-callback sets no consumer queue"
    assert AGENT_KV_CALLBACK_QUEUE in _queues(raw), (
        f"{AGENT_KV_CALLBACK_QUEUE} has no consumer -- Agent-KV jobs will "
        f"finish executing and never leave RUNNING."
    )


def test_run_worker_pg_ide_callback_role_drains_the_callback_queue():
    text = RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_IDE_CALLBACK"\]="ide_callback;([^"]+)"', text)
    assert match, "could not find the PG_ROLE_IDE_CALLBACK entry in run-worker.sh"
    assert AGENT_KV_CALLBACK_QUEUE in _queues(match.group(1))


# --------------------------------------------------------------------------
# Traefik routing. Same family of failure as an unconsumed queue: the service
# is up, the route looks configured, and the request lands somewhere that
# cannot serve it.
#
# `/agent-kv/` is mounted by `backend/backend/base_urls.py`, but traefik's
# backend rule matched only `/api/v1`, `/deployment` and `/public`, and the
# frontend rule is the negation of exactly those -- so every Agent-KV request
# through the compose stack was served by the SPA's nginx and never reached
# Django. The e2e lane did not catch it because it talks to
# `UNSTRACT_BACKEND_URL` (port 8000) directly, bypassing traefik entirely.
#
# Reported as 2.2 in the branch review.
# --------------------------------------------------------------------------

AGENT_KV_PREFIX = "/agent-kv"


def _router_rule(compose_path: Path, router: str) -> str:
    svc_labels = []
    for svc in yaml.safe_load(compose_path.read_text())["services"].values():
        svc_labels.extend(svc.get("labels") or [])
    prefix = f"traefik.http.routers.{router}.rule="
    for label in svc_labels:
        if isinstance(label, str) and label.startswith(prefix):
            return label[len(prefix) :]
    pytest.fail(f"no traefik rule for router {router!r} in {compose_path.name}")


def test_traefik_routes_agent_kv_to_the_backend():
    rule = _router_rule(DEV_COMPOSE, "backend")
    assert f"PathPrefix(`{AGENT_KV_PREFIX}`)" in rule, (
        "traefik does not route /agent-kv to the backend; the request is served "
        "by the frontend SPA and never reaches Django"
    )


def test_traefik_excludes_agent_kv_from_the_frontend():
    """The frontend rule is a negation list, so a prefix missing from it is
    claimed by the SPA even once the backend also matches -- whichever router
    wins, one of them is wrong.
    """
    rule = _router_rule(DEV_COMPOSE, "frontend")
    assert f"!PathPrefix(`{AGENT_KV_PREFIX}`)" in rule, (
        "the frontend router still claims /agent-kv; it must be excluded "
        "explicitly, exactly as /api/v1, /deployment and /public are"
    )


def test_every_backend_prefix_is_excluded_from_the_frontend():
    """The two rules are each other's complement by construction. Asserting the
    relationship rather than one hardcoded prefix means the next mount point
    cannot be added to one side only.
    """
    backend_rule = _router_rule(DEV_COMPOSE, "backend")
    frontend_rule = _router_rule(DEV_COMPOSE, "frontend")

    backend_prefixes = set(re.findall(r"PathPrefix\(`([^`]+)`\)", backend_rule))
    excluded = set(re.findall(r"!PathPrefix\(`([^`]+)`\)", frontend_rule))

    missing = backend_prefixes - excluded
    assert not missing, (
        f"{sorted(missing)} route to the backend but are not excluded from the "
        f"frontend router; the SPA will claim them"
    )
