"""Fleet queue wiring, DERIVED from `EXTRACTOR_ROUTES` rather than literal-pinned.

`workers/tests/test_queue_consumer_wiring.py` guards the same property with
hardcoded queue names (`UNSERVED_KV_QUEUE`, `AGENT_TABLE_QUEUE`). That works
today and catches a real, expensive failure -- but it cannot survive the change
it most needs to survive. Re-enabling the `kv` extractor means adding one entry
to `EXTRACTOR_ROUTES`, at which point `celery_executor_agentic_kv` flips from
"must NOT be advertised" to "must be served", and the literal-pinned assertion
has to be *deleted* to make the suite pass. An assertion whose correct response
to a change is deletion is not protecting anything at that moment.

This suite derives both directions from the routing table, so the same change
flips the expectation automatically:

* Every executor in `EXTRACTOR_ROUTES` must have its `celery_executor_<name>`
  queue served by every fleet configuration. Unserved means jobs are accepted
  and sit in DISPATCHED forever -- `enqueue_task` succeeds, rows land in
  `pg_queue_message`, nothing errors at the producer.
* Every executor this module names but deliberately does NOT route
  (`EXECUTOR_NAME` = `agentic_kv`, kept dormant by the carve-out) must NOT be
  advertised anywhere. Same silent failure from the other side.

Lives in the backend suite because that is where `EXTRACTOR_ROUTES` is
importable; the fleet configs it reads are plain text. The workers-side suite
keeps its literal assertions as a cheap second opinion -- two independent
statements of the same fact, which is the point.

**Every path is guarded by `pytest.skip` when absent.** A cross-tree read that
assumed a file existed has reddened CI on this branch once already: the backend
test venv runs from `backend/`, and nothing guarantees a packaging step kept
`docker/` or `workers/` alongside it.
"""

import re
from pathlib import Path

import pytest
import yaml

from agent_kv.constants import (
    EXECUTOR_NAME,
    EXTRACTOR_ROUTES,
    TABLE_EXECUTOR_NAME,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_COMPOSE = REPO_ROOT / "docker" / "docker-compose.yaml"
TEST_COMPOSE = REPO_ROOT / "tests" / "compose" / "docker-compose.test.yaml"
RUN_WORKER = REPO_ROOT / "workers" / "run-worker.sh"
RUN_WORKER_DOCKER = REPO_ROOT / "workers" / "run-worker-docker.sh"

PG_QUEUE_VAR = "WORKER_PG_QUEUE_CONSUMER_QUEUE"

#: Every executor name this module knows about. The ones in `EXTRACTOR_ROUTES`
#: must be served; the rest must not be advertised. Derived, so adding a route
#: moves a name from one set to the other with no edit here.
ALL_KNOWN_EXECUTORS = {EXECUTOR_NAME, TABLE_EXECUTOR_NAME}


def _queue_name(executor: str) -> str:
    """How `pg_queue` derives a queue from an executor name.

    Mirrors the dispatcher's own derivation. If that convention changes, every
    assertion here goes stale together rather than one at a time.
    """
    return f"celery_executor_{executor}"


def _routed_executors() -> set[str]:
    return {executor for executor, _operation in EXTRACTOR_ROUTES.values()}


def _unrouted_executors() -> set[str]:
    return ALL_KNOWN_EXECUTORS - _routed_executors()


def _require(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path} is not present in this tree")
    return path.read_text()


def _queues(raw: str) -> set[str]:
    """Queue names from a consumer list, ignoring a `${VAR:-default}` wrapper."""
    inner = re.sub(r"^\$\{[^:}]+:-(.*)\}$", r"\1", raw.strip())
    return {q.strip() for q in inner.split(",") if q.strip()}


def _compose_executor_queues(path: Path) -> set[str]:
    doc = yaml.safe_load(_require(path))
    env = (doc.get("services", {}).get("worker-pg-executor") or {}).get(
        "environment"
    ) or []
    if isinstance(env, dict):
        values = {k: str(v) for k, v in env.items()}
    else:
        values = {}
        for item in env:
            key, _, value = str(item).partition("=")
            values[key] = value
    raw = values.get(PG_QUEUE_VAR)
    assert raw is not None, (
        f"{path.name}: worker-pg-executor sets no {PG_QUEUE_VAR}, so the "
        f"running pg-queue-consumer falls back to a default of unknown content"
    )
    return _queues(raw)


def _shell_role_queues(path: Path, pattern: str) -> set[str]:
    match = re.search(pattern, _require(path))
    assert match, f"could not find {pattern!r} in {path.name}"
    return _queues(match.group(1))


#: Every place a fleet declares which executor queues it drains. The two shell
#: runners are included because a queue missing from a launcher is exactly as
#: undrained as one missing from compose -- and `run-worker-docker.sh` was
#: guarded by nothing at all.
def _all_executor_fleets() -> dict:
    return {
        "dev compose": lambda: _compose_executor_queues(DEV_COMPOSE),
        "e2e test compose": lambda: _compose_executor_queues(TEST_COMPOSE),
        "run-worker.sh": lambda: _shell_role_queues(
            RUN_WORKER, r'\["\$PG_ROLE_EXECUTOR"\]="executor;([^"]+)"'
        ),
    }


@pytest.mark.parametrize("fleet", sorted(_all_executor_fleets()))
def test_every_routed_executor_has_a_consumer(fleet):
    """The forward direction, derived.

    A route with no consumer accepts work and drains nothing, silently -- the
    failure that cost this team ~30 hours of firings with zero executions.
    """
    served = _all_executor_fleets()[fleet]()
    expected = {_queue_name(e) for e in _routed_executors()}

    missing = expected - served
    assert not missing, (
        f"{fleet} serves none of {sorted(missing)}, but EXTRACTOR_ROUTES "
        f"dispatches there. Jobs will be accepted and sit in DISPATCHED "
        f"forever with no error at the producer."
    )


@pytest.mark.parametrize("fleet", sorted(_all_executor_fleets()))
def test_no_fleet_advertises_an_unrouted_executor(fleet):
    """The inverse direction, derived.

    `agentic_kv` is the live case: this deployment ships no such plugin, so a
    fleet listing its queue would accept work nothing can drain. When `kv` is
    re-enabled by adding its `EXTRACTOR_ROUTES` entry, this expectation inverts
    on its own and `test_every_routed_executor_has_a_consumer` starts requiring
    the queue instead -- which is the whole reason this is derived.
    """
    served = _all_executor_fleets()[fleet]()
    forbidden = {_queue_name(e) for e in _unrouted_executors()}

    advertised = forbidden & served
    assert not advertised, (
        f"{fleet} advertises {sorted(advertised)}, but no EXTRACTOR_ROUTES "
        f"entry dispatches there and this deployment carries no such plugin. "
        f"Remove it, or add the route and ship the plugin."
    )


def test_the_derivation_is_not_vacuous():
    """Both sets must be non-empty, or the two tests above assert nothing.

    If `EXTRACTOR_ROUTES` were emptied, `test_every_routed_executor_...` would
    pass with an empty expectation -- green while nothing was wired. If every
    known executor were routed, the inverse test would pass trivially. This is
    the guard on the guards.
    """
    assert _routed_executors(), "no routed executors: the forward test is vacuous"
    assert _unrouted_executors(), (
        "every known executor is routed, so the inverse test is vacuous. If "
        "`kv` was deliberately re-enabled, that is correct -- delete this "
        "assertion and say so."
    )


# ---------------------------------------------------------------------------
# The callback queue, across BOTH launchers.
#
# `run-worker-docker.sh` carries its own `["ide_callback"]=
# "ide_callback,agent_kv_callback"` map and was guarded by nothing: dropping
# `agent_kv_callback` there passed every test in the tree while a
# docker-launched fleet drained no terminal callbacks, leaving every job
# RUNNING forever.
# ---------------------------------------------------------------------------

CALLBACK_QUEUE = "agent_kv_callback"


def test_the_docker_launcher_drains_the_terminal_callback_queue():
    """The launcher the workers-side suite does not cover."""
    queues = _shell_role_queues(
        RUN_WORKER_DOCKER, r'\["ide_callback"\]="([^"]+)"'
    )

    assert CALLBACK_QUEUE in queues, (
        f"run-worker-docker.sh's ide_callback role omits {CALLBACK_QUEUE}; a "
        f"docker-launched fleet would run jobs to completion and never "
        f"terminalize them -- finalize is what persists the result, deletes "
        f"the staged input, releases the slot and fires the webhook."
    )


def test_the_host_launcher_drains_the_terminal_callback_queue():
    """Already covered on the workers side; repeated here so the two launchers
    are asserted side by side and a reader can see neither is missing.
    """
    queues = _shell_role_queues(
        RUN_WORKER, r'\["\$PG_ROLE_IDE_CALLBACK"\]="ide_callback;([^"]+)"'
    )

    assert CALLBACK_QUEUE in queues


# ---------------------------------------------------------------------------
# The billing backstop, DERIVED from `EXTRACTOR_ROUTES` the same way.
#
# `executor.tasks._LLM_BEARING_OPS` is the set of operations that must log when
# a successful run emits no usage records. That log line is the ONLY signal of
# total billing loss: the cloud `flush()` returns an empty list rather than
# raising, so "the billing chain broke" and "this job legitimately made no LLM
# calls" are otherwise indistinguishable. An op missing from the set is a
# missing ALARM, and the symptom is silence.
#
# `workers/tests/test_llm_bearing_ops.py` guards it against a hand-maintained
# `PAID_OPERATIONS` twin, which enforces symmetry between two literals -- so it
# can only fail when the copies DISAGREE, never when both are wrong together. A
# new paid extractor added to `EXTRACTOR_ROUTES` and declared in neither list
# ships with no billing alarm and nothing goes red.
#
# Every operation this API routes drives LLM calls by construction -- that is
# what an Agent-KV extractor IS -- so the set can be derived rather than
# declared.
#
# Read as TEXT and parsed with `ast`, not imported: `executor.tasks` is a
# workers package and is not importable from the backend's test venv (the
# mirror of why the workers-side suite cannot import `EXTRACTOR_ROUTES`). An
# import would make this pass vacuously in exactly the environment where the
# drift happens. Skipped if the file is absent from this tree.
# ---------------------------------------------------------------------------

EXECUTOR_TASKS = REPO_ROOT / "workers" / "executor" / "tasks.py"


def _llm_bearing_ops_literal() -> set[str]:
    """Pull `_LLM_BEARING_OPS`' string members out of the source."""
    import ast

    tree = ast.parse(_require(EXECUTOR_TASKS))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_LLM_BEARING_OPS" not in targets:
            continue
        return {
            element.value
            for element in ast.walk(node.value)
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    pytest.fail(f"no `_LLM_BEARING_OPS` assignment found in {EXECUTOR_TASKS}")


def test_every_routed_operation_has_a_billing_backstop():
    """The derived assertion the two literal lists cannot make.

    Add an extractor to `EXTRACTOR_ROUTES` and forget the backstop, and this
    fails -- without anyone having had to remember a second list.
    """
    declared = _llm_bearing_ops_literal()
    routed_ops = {operation for _executor, operation in EXTRACTOR_ROUTES.values()}

    missing = routed_ops - declared
    assert not missing, (
        f"{sorted(missing)} are routed by EXTRACTOR_ROUTES but absent from "
        f"`_LLM_BEARING_OPS` in workers/executor/tasks.py. Every Agent-KV "
        f"extractor drives LLM calls, so a run of one that emits zero usage "
        f"records means the billing chain broke -- and without the set "
        f"membership, nothing logs it. Add the op there (and to "
        f"workers/tests/test_llm_bearing_ops.py's PAID_OPERATIONS)."
    )


def test_the_backstop_derivation_is_not_vacuous():
    """If the AST parse silently returned nothing, the test above would pass."""
    assert _llm_bearing_ops_literal(), (
        "parsed no operation names out of `_LLM_BEARING_OPS` -- the assignment "
        "shape changed and the derivation above is now asserting against an "
        "empty set"
    )
