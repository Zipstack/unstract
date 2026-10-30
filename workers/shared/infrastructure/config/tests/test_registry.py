"""Tests for worker registry configuration.

The registry is where a queue stops being a string in a shell script and
becomes something a worker actually subscribes to. For Agent-KV that matters
more than usual: `agent_kv_callback` carries the terminal callbacks, and a job
whose callback is never consumed runs to SUCCESS in the executor and then sits
in RUNNING forever -- the result is never persisted, the staged input is never
deleted, the concurrency slot is never released and the webhook never fires.
Nothing errors, because nothing failed.
"""

from shared.enums.worker_enums import WorkerType
from shared.enums.worker_enums_base import QueueName
from shared.infrastructure.config.registry import WorkerRegistry


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
