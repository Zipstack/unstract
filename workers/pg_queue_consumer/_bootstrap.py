"""Shared bootstrap for the PG-queue consumer entrypoints.

Both the single-process launcher (``__main__``) and the prefork supervisor's
children must select the source worker type *before* ``import worker`` (which
reads ``WORKER_TYPE`` at import time to register that type's tasks). Kept in a
neutral module — not ``__main__`` — so ``supervisor`` can import it without
triggering the ``python -m`` entry.

Also home to :func:`drop_dumpable_for_untrusted_code_pools`, which must run in
the launcher process (PID 1) before the supervisor forks — see its docstring for
why it cannot live in ``workers/sandbox/``.
"""

import ctypes
import logging
import os
import sys

logger = logging.getLogger(__name__)


def select_source_worker_type() -> None:
    """Point ``WORKER_TYPE`` at the source worker whose tasks back this consumer.

    Overwrites (not ``setdefault``): the launcher's own ``WORKER_TYPE`` is the
    ``pg_queue_consumer`` pseudo-type, which owns no tasks — a plain ``import
    worker`` would fall back to the ``general`` worker and drop every message as an
    unknown task. Default ``notification`` (the worker owning the first migrated
    leaf task). Must run before ``import worker``.
    """
    os.environ["WORKER_TYPE"] = os.environ.get(
        "WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE", "notification"
    )


# --- /proc hardening for pools that run untrusted code (UN-4044, R12) -------

#: ``prctl(2)`` ``PR_SET_DUMPABLE`` with ``SUID_DUMP_DISABLE``. Clearing the
#: dumpable flag re-owns ``/proc/<pid>/{environ,mem,maps,…}`` to root, so a
#: same-UID reader without ``CAP_SYS_PTRACE`` is refused.
_PR_SET_DUMPABLE = 4
_SUID_DUMP_DISABLE = 0

#: Source worker types whose pool executes tenant-influenced, LLM-generated
#: Python. Matched against ``WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE`` — the chart
#: value (``workerPgSandbox.env``), NOT the ``WORKER_TYPE`` that
#: :func:`select_source_worker_type` derives from it, because this runs before
#: that call on the supervisor path.
_UNTRUSTED_CODE_WORKER_TYPES = frozenset({"sandbox"})


def _resolve_prctl():
    """Bind ``libc.prctl``, or return ``None`` where that is not possible.

    Deliberately a second, local copy of ``sandbox/runner.py``'s resolver rather
    than an import of it: this module is imported by EVERY pg-queue consumer
    pool, and importing the sandbox package here would pull the sandbox's
    dependencies into pools that have no business loading them.

    ``CDLL(None)`` resolves through the process's own symbol table instead of a
    hardcoded ``libc.so.6``, which does not exist on a musl base.
    """
    if not sys.platform.startswith("linux"):
        # Not a warning: PR_SET_DUMPABLE is a Linux facility, so its absence
        # off Linux is expected rather than a misconfiguration.
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
    except (OSError, AttributeError):
        return None
    prctl.restype = ctypes.c_int
    prctl.argtypes = (ctypes.c_int,) + (ctypes.c_ulong,) * 4
    return prctl


def drop_dumpable_for_untrusted_code_pools() -> None:
    """Make this process's ``/proc`` entries unreadable to its own children.

    **What this closes.** The sandbox pool mounts the shared ``database``
    config group, so ``DB_PASSWORD`` is in this process's environment — on the
    PG transport the queue *is* Postgres, so the pod must hold a DB credential
    (accepted residual **R12** in ``docs/agent-kv-architecture.md``). The
    generated script that ``sandbox/runner.py`` spawns gets a scrubbed
    environment, but it runs under this same UID, and the AST gate permits
    ``open()`` BY DESIGN — generated code has to read its input file. So
    ``open('/proc/<ppid>/environ')`` returned this process's full environment
    using nothing but ``open()`` and string slicing: no gate bypass, and no
    import. Measured both ways — the read succeeds with the flag set and raises
    ``PermissionError`` once it is cleared.

    **Why here and not in ``workers/sandbox/``.** On the ``CONCURRENCY > 1``
    path the supervisor forks children that each run their own ``import
    worker``; the supervisor itself never imports the sandbox package. A call
    sited in the sandbox module would therefore leave PID 1 — which holds the
    same environment — readable. Called from ``__main__`` before the
    concurrency branch, this covers PID 1 on both paths, and the flag is
    inherited across ``fork``, so the children need no call of their own.

    **Ordering.** ``execve`` resets the dumpable flag, so this must run after
    the entrypoint's ``exec "$PG_QUEUE_PYTHON_BIN" -m pg_queue_consumer``
    (``run-worker-docker.sh``) — it does, being Python in the exec'd process —
    and before the supervisor forks.

    **Best-effort, matching ``runner.py``'s treatment of ``PR_SET_PDEATHSIG``.**
    A pool that cannot clear the flag still starts, because this is
    defence-in-depth and not the control that gates the exposure: the chart's
    ``validate-sandbox-db-credential`` guard refuses to render
    ``AGENT_KV_CALCULATIONS_ENABLED=true`` while the shared credential is
    mounted, so untrusted code does not execute at all until either that
    credential is narrowed (**UN-4218**) or the flag is flipped deliberately.

    **What it does NOT fix.** The credential is still in the pod — UN-4218's
    least-privilege role remains the structural fix. This also protects only
    the *environment*: a secret delivered as a FILE would be readable by
    ``open()`` whatever the dumpable flag says. That the pod has none today is
    a property of its spec (every secret arrives via ``envFrom``, the only
    volume is a ``/tmp`` emptyDir, and ``automountServiceAccountToken`` is
    ``false``) and would need re-checking if that spec gains a secret volume.

    A cleared flag also disables core dumps and blocks ``ptrace``-based
    attachment (``py-spy``, ``gdb``) for this pod.
    """
    worker_type = os.environ.get("WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE", "")
    if worker_type not in _UNTRUSTED_CODE_WORKER_TYPES:
        return

    prctl = _resolve_prctl()
    if prctl is None:
        logger.warning(
            "pg-queue-consumer[%s]: prctl could not be resolved, so this "
            "process's /proc entries stay readable by its own children and a "
            "generated script can recover DB_PASSWORD from "
            "/proc/<ppid>/environ. See R12.",
            worker_type,
        )
        return

    if prctl(_PR_SET_DUMPABLE, _SUID_DUMP_DISABLE, 0, 0, 0) != 0:
        logger.warning(
            "pg-queue-consumer[%s]: PR_SET_DUMPABLE failed (errno=%d); this "
            "process's /proc entries stay readable by its own children. "
            "See R12.",
            worker_type,
            ctypes.get_errno(),
        )
        return

    logger.info(
        "pg-queue-consumer[%s]: cleared the dumpable flag; /proc/<pid>/environ "
        "is no longer readable by this process's own children.",
        worker_type,
    )
