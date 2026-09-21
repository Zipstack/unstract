"""Executor implementations package.

Registration is **explicit**: call :func:`register_all`. It used to run as a
side effect of importing this package, which meant that importing *any*
submodule — including ``executor.executors.constants``, which itself imports
nothing but ``enum`` — dragged in ``LegacyExecutor`` and the entire adapter
stack behind it. That cost ~9s, and the file_processing worker paid it once per
forked child just to read a few string constants (UN-4136).

``executor/tasks.py`` is the only caller: ``workers/worker.py`` exec-loads that
file by path for both the Celery and PG executor roles. ``executor/worker.py``
reaches it transitively, by importing ``executor.tasks`` — that import is
load-bearing despite its ``noqa: F401``, and removing it would leave the app it
builds with an empty registry.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from executor.executors.legacy_executor import LegacyExecutor  # noqa: TCH004

#: Cloud entry point names, or None until discovery has run. Doubles as the
#: re-entrancy latch — see the comment in :func:`register_all`.
_cloud_executors: list[str] | None = None


def register_all() -> list[str]:
    """Import the executor modules once per process, registering each of them.

    ``LegacyExecutor`` and every cloud executor carry
    ``@ExecutorRegistry.register``, which fires when their module is first
    imported. That is the whole mechanism, and it bounds the guarantee: this
    populates ``ExecutorRegistry`` **in a fresh process**, and cannot repopulate
    it if something empties it afterwards, because the second import is a
    ``sys.modules`` hit and the decorator does not run again. Production never
    clears the registry. Several test modules do, and most of them do not put it
    back — ``tests/test_legacy_executor_scaffold.py`` is the one that restores
    what it cleared, and is the pattern to copy.

    Idempotent, and safe to re-enter: a cloud plugin whose own import graph
    reaches this function during ``ep.load()`` will not restart discovery.

    Returns:
        The cloud executor entry point names, as a fresh copy each time so a
        caller cannot mutate the latched state.

        An empty list does not distinguish its causes: no cloud plugins are
        installed (the OSS case); every one of them failed to import, because
        ``ExecutorPluginLoader.discover_executors`` catches per-entry-point
        failures and only logs a warning — so a broken plugin wheel boots clean
        and surfaces later as "No executor registered with name 'table'" on each
        dispatch (tracked on UN-4136); or the caller is *inside* discovery,
        having re-entered while the latch is still the empty placeholder.
    """
    global _cloud_executors

    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401

    if _cloud_executors is None:
        from executor.executors.plugins.loader import ExecutorPluginLoader

        # Latch BEFORE discovering. ``ep.load()`` executes third-party code, and
        # a plugin that reaches back into this function would otherwise find the
        # latch still unset and restart the entry point loop, nesting once per
        # level. The import-side-effect version this replaced got that safety
        # free from ``sys.modules``.
        #
        # A failure here leaves the latch at ``[]``. That is deliberate: the one
        # caller runs at ``executor/tasks.py`` module scope, so the exception
        # kills the boot and the process restarts with clean module state.
        # Retrying in-process would be worse than useless — a plugin whose
        # ``@ExecutorRegistry.register`` fired before it raised is evicted from
        # ``sys.modules`` but left in the registry, so re-importing it raises a
        # duplicate-name ``ValueError`` that ``discover_executors`` swallows into
        # a warning, and that executor is then silently absent for the life of
        # the process. Do not add a retry without fixing that first.
        _cloud_executors = []
        _cloud_executors = ExecutorPluginLoader.discover_executors()

    return list(_cloud_executors)


def __getattr__(name: str) -> object:
    """Keep ``from executor.executors import LegacyExecutor`` working.

    The class used to sit in this namespace as a side effect of the eager
    import. Resolving it on access preserves that spelling without reviving the
    cost for everyone who imports a sibling submodule.
    """
    if name == "LegacyExecutor":
        from executor.executors.legacy_executor import LegacyExecutor

        return LegacyExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reset_discovery_for_tests() -> None:
    """Re-arm entry point discovery so a test can observe it running again.

    Discovery only. This does **not** restore the bundled executor: that is
    registered by module import, which cannot be made to happen twice in one
    process. A test that clears ``ExecutorRegistry`` must re-register
    explicitly, as ``tests/test_legacy_executor_scaffold.py`` does.
    """
    global _cloud_executors
    _cloud_executors = None


__all__ = ["LegacyExecutor", "register_all"]
