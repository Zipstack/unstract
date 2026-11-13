"""Tests for worker registry configuration.

The registry is where a queue stops being a string in a shell script and
becomes something a worker actually subscribes to. For Agent-KV that matters
more than usual: `agent_kv_callback` carries the terminal callbacks, and a job
whose callback is never consumed runs to SUCCESS in the executor and then sits
in RUNNING forever -- the result is never persisted, the staged input is never
deleted, the concurrency slot is never released and the webhook never fires.
Nothing errors, because nothing failed.
"""

import re
from pathlib import Path

import yaml
from shared.enums.worker_enums import WorkerType
from shared.enums.worker_enums_base import QueueName
from shared.infrastructure.config.registry import WorkerRegistry

#: Repo root, from workers/shared/infrastructure/config/tests/ -> up five.
#: Asserted rather than trusted: a file move would otherwise make the reads
#: below silently skip, and a test that cannot find its inputs must fail, not
#: pass.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEV_COMPOSE = _REPO_ROOT / "docker" / "docker-compose.yaml"
_RUN_WORKER = _REPO_ROOT / "workers" / "run-worker.sh"


def test_sandbox_worker_registered():
    cfg = WorkerRegistry._QUEUE_CONFIGS[WorkerType.SANDBOX]
    assert cfg.primary_queue == QueueName.SANDBOX_CODEGEN


def test_sandbox_task_route():
    routing = WorkerRegistry._TASK_ROUTES[WorkerType.SANDBOX]
    routed = {r.pattern: r.queue for r in routing.routes}
    assert routed["execute_sandboxed_code"] == QueueName.SANDBOX_CODEGEN


def test_ide_callback_worker_also_subscribes_to_the_agent_kv_callback_queue():
    cfg = WorkerRegistry._QUEUE_CONFIGS[WorkerType.IDE_CALLBACK]
    assert QueueName.AGENT_KV_CALLBACK in cfg.additional_queues, (
        "the ide_callback worker does not subscribe to agent_kv_callback; "
        "Agent-KV jobs would execute and then never terminalize"
    )


def test_both_agent_kv_terminal_callbacks_route_to_that_queue():
    """`dispatch_job` attaches both as Celery link/link_error. A route missing
    for either leaves one half of the outcome space unhandled -- most visibly,
    a failed job that never moves out of RUNNING.
    """
    routing = WorkerRegistry._TASK_ROUTES[WorkerType.IDE_CALLBACK]
    routed = {r.pattern: r.queue for r in routing.routes}

    assert routed["agent_kv_complete"] == QueueName.AGENT_KV_CALLBACK
    assert routed["agent_kv_error"] == QueueName.AGENT_KV_CALLBACK


def test_the_sandbox_queue_is_claimed_now_that_the_sandbox_ships():
    """Inverted from main's `test_no_worker_type_claims_the_unshipped_sandbox_queue`.

    That guard existed because the table-only slice (UN-4232) shipped the API
    without a codegen sandbox, and "a registry entry for a worker that is never
    deployed is how a queue ends up advertised and undrained". This PR is the
    change that deploys it, so the same concern now points the other way: the
    queue must be claimed, or `execute_sandboxed_code` is enqueued and nothing
    drains it. Kept as an explicit assertion rather than deleted, so the
    transition is visible in the history instead of looking like a lost test.
    """
    assert hasattr(QueueName, "SANDBOX_CODEGEN")
    assert hasattr(WorkerType, "SANDBOX")
    assert WorkerType.SANDBOX in WorkerRegistry._QUEUE_CONFIGS


def test_the_deployment_configs_name_the_queue_the_registry_claims():
    """Ties the SHIPPED consumer's queue strings to ``QueueName.SANDBOX_CODEGEN``.

    The guard above asserts the registry CLAIMS the queue. That is a fact about
    ``_QUEUE_CONFIGS`` and says nothing about what the deployed consumer
    actually drains: the live consumer reads
    ``WORKER_PG_QUEUE_CONSUMER_QUEUE`` from ``docker/docker-compose.yaml`` and
    the ``pg-sandbox`` role from ``workers/run-worker.sh``, and nothing tied
    either of those strings to the enum. A rename on one side would leave
    ``execute_sandboxed_code`` enqueued onto a queue nothing drains -- no error
    at the producer, no failed pod, the job simply never runs. Reported as a
    High on #2309.

    DERIVED, not another literal, and that is the point of putting it here:
    this module can import ``QueueName``, which
    ``workers/tests/test_queue_consumer_wiring.py`` cannot -- its own header
    records that asymmetry as the reason its sandbox assertions are string
    literals. So the literal/enum tie belongs on this side of the venv split.

    The test-compose overlay is deliberately NOT asserted on: it is an overlay
    (``tests/rig/runtime.COMPOSE_OVERLAY``) applied over the dev compose and
    sets only an image, a grace period and four tuning vars, so it inherits the
    queue rather than restating it. Requiring it here would pin a value that
    file has no business carrying.
    """
    # `.value`, not `str()`: QueueName is `(str, Enum)`, so `str()` renders
    # "QueueName.SANDBOX_CODEGEN" rather than the queue name, and the compose
    # comparison below would never match. This assertion caught that on its
    # first run, which is the behaviour wanted from it.
    queue = QueueName.SANDBOX_CODEGEN.value

    assert _DEV_COMPOSE.is_file(), f"dev compose not found at {_DEV_COMPOSE}"
    services = yaml.safe_load(_DEV_COMPOSE.read_text())["services"]
    assert "worker-sandbox" in services, sorted(services)
    env = services["worker-sandbox"].get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env if "=" in str(item))
    composed = str(env.get("WORKER_PG_QUEUE_CONSUMER_QUEUE") or "")
    assert queue in {q.strip() for q in composed.split(",") if q.strip()}, (
        f"docker-compose.yaml's worker-sandbox drains {composed!r}, which does "
        f"not include {queue!r} -- execute_sandboxed_code would be enqueued "
        "onto a queue nothing serves"
    )

    assert _RUN_WORKER.is_file(), f"run-worker.sh not found at {_RUN_WORKER}"
    text = _RUN_WORKER.read_text()
    match = re.search(r'\["\$PG_ROLE_SANDBOX"\]="sandbox;([^"]+)"', text)
    assert match, "could not find the PG_ROLE_SANDBOX queue mapping in run-worker.sh"
    assert queue in {q.strip() for q in match.group(1).split(",") if q.strip()}, (
        f"run-worker.sh's pg-sandbox role lists {match.group(1)!r}, which does "
        f"not include {queue!r}"
    )


def test_the_sandbox_route_names_a_task_that_actually_exists():
    """Ties the route literal to the registered task, which nothing did.

    `test_sandbox_route` compares the literal in `registry.py` against a
    literal in the test, so the two could disagree with the decorator in
    `sandbox/tasks.py` and both stay green. A typo in either declaration
    produces the failure this feature's comments cite repeatedly: work enqueued
    onto a served queue, no task registered under that name, nothing at the
    producer.

    (The same gap exists for every other worker; closing it here is a
    precedent, not a claim that this PR introduced it.)
    """
    import sandbox.tasks  # noqa: F401 -- importing registers the task
    from shared.infrastructure.config.registry import WorkerRegistry

    routed = {r.pattern for r in WorkerRegistry._TASK_ROUTES[WorkerType.SANDBOX].routes}
    registered = {sandbox.tasks.execute_sandboxed_code.name}
    missing = routed - registered
    assert not missing, (
        f"registry.py routes {sorted(missing)}, but sandbox.tasks registers "
        f"{sorted(registered)} -- work on that queue would find no handler"
    )
