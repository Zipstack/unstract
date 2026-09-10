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

# The queue the backend dispatches Agent-KV extraction onto
# (ExecutionContext(executor_name="agentic_kv") -> celery_executor_agentic_kv).
AGENT_KV_QUEUE = "celery_executor_agentic_kv"

# The terminal-callback queue. Its consumer is what moves a job out of
# RUNNING: finalize persists the result, deletes the staged input, releases
# the concurrency slot and fires the webhook.
AGENT_KV_CALLBACK_QUEUE = "agent_kv_callback"

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
    wrapper the compose file uses to keep the value overridable."""
    inner = re.sub(r"^\$\{[^:}]+:-(.*)\}$", r"\1", raw.strip())
    return {q.strip() for q in inner.split(",") if q.strip()}


@pytest.mark.parametrize(
    ("compose_path", "label"),
    [(DEV_COMPOSE, "dev compose"), (TEST_COMPOSE, "e2e test compose")],
)
def test_pg_executor_consumes_the_agent_kv_queue(compose_path, label):
    """The PG executor must drain celery_executor_agentic_kv in both stacks."""
    env = _service_env(compose_path, "worker-pg-executor")
    raw = env.get(PG_QUEUE_VAR)
    assert raw is not None, (
        f"{label}: worker-pg-executor sets no {PG_QUEUE_VAR}; the running "
        f"pg-queue-consumer would fall back to a default that omits "
        f"{AGENT_KV_QUEUE}"
    )
    assert AGENT_KV_QUEUE in _queues(raw), (
        f"{label}: {AGENT_KV_QUEUE} has no consumer -- Agent-KV jobs will sit "
        f"in DISPATCHED forever with no error at the producer. Add it to "
        f"{PG_QUEUE_VAR}."
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


def test_run_worker_pg_executor_role_lists_the_agent_kv_queue():
    """The host-run fleet's hardcoded role default must match the compose stacks.

    ``run-worker.sh`` carries its own PG_CONSUMER_ROLES map; a queue added to
    compose but not here is unconsumed for anyone running the fleet directly.
    """
    text = RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_EXECUTOR"\]="executor;([^"]+)"', text)
    assert match, "could not find the PG_ROLE_EXECUTOR entry in run-worker.sh"
    assert AGENT_KV_QUEUE in _queues(match.group(1)), (
        f"run-worker.sh's pg-executor role omits {AGENT_KV_QUEUE}; a host-run "
        f"fleet would accept Agent-KV work and never drain it."
    )


# --------------------------------------------------------------------------
# The codegen sandbox: same silent-drop risk, plus a security posture that must
# survive any future "simplification" onto the shared PG worker template.
# --------------------------------------------------------------------------

SANDBOX_QUEUE = "sandbox_codegen"


def test_sandbox_drains_its_queue_over_the_pg_transport():
    """The sandbox must consume sandbox_codegen on PG, not the retired broker."""
    svc = yaml.safe_load(DEV_COMPOSE.read_text())["services"]["worker-sandbox"]
    assert svc.get("command") == ["pg-queue-consumer"], (
        "worker-sandbox is not running the PG consumer; on the broker it would "
        "drain nothing once the transport flips, with no error at the producer."
    )
    env = _service_env(DEV_COMPOSE, "worker-sandbox")
    assert env.get("WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE") == "sandbox", (
        "the consumer must load the sandbox worker's tasks.py, else "
        "execute_sandboxed_code is not registered and every message is dropped "
        "as an unknown task_name"
    )
    assert SANDBOX_QUEUE in _queues(env.get("WORKER_PG_QUEUE_CONSUMER_QUEUE", ""))


def test_sandbox_does_not_depend_on_the_retired_broker():
    svc = yaml.safe_load(DEV_COMPOSE.read_text())["services"]["worker-sandbox"]
    assert "rabbitmq" not in (svc.get("depends_on") or []), (
        "UN-4046 retired RabbitMQ as the task transport; the sandbox must not "
        "reintroduce a dependency on it."
    )


def test_run_worker_has_a_pg_sandbox_role():
    text = RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_SANDBOX"\]="sandbox;([^"]+)"', text)
    assert match, "run-worker.sh has no pg-sandbox PG_CONSUMER_ROLES entry"
    assert SANDBOX_QUEUE in _queues(match.group(1))


def test_sandbox_hardening_is_preserved():
    """Security guard for spec §6.3 layer 3.

    The sandbox executes attacker-influenced generated code, so its pod-level
    hardening is load-bearing -- the AST gate is explicitly *not* the boundary.
    The shared PG worker template (``_pg-worker.tpl``) cannot express any of
    these, so a future move onto it would silently drop them. Fail loudly first.
    """
    svc = yaml.safe_load(DEV_COMPOSE.read_text())["services"]["worker-sandbox"]
    assert svc.get("read_only") is True, "read-only rootfs lost"
    assert "no-new-privileges:true" in (svc.get("security_opt") or []), (
        "no-new-privileges lost"
    )
    assert "ALL" in (svc.get("cap_drop") or []), "cap_drop: ALL lost"
    assert "/tmp" in (svc.get("tmpfs") or []), "writable /tmp scratch lost"
    assert not svc.get("ports"), (
        "the sandbox must publish no ports; its health endpoint is internal-only"
    )
    assert not svc.get("extra_hosts"), (
        "the sandbox must not get host_gateway — it must not reach the host"
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
