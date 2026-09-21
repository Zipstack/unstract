"""Executor implementations package.

Registration is **explicit**: call :func:`register_all`. It used to run as a
side effect of importing this package, which meant that importing *any*
submodule — including ``executor.executors.constants``, which itself imports
nothing but ``enum`` — dragged in ``LegacyExecutor`` and the entire adapter
stack behind it. That cost ~9s, and the file_processing worker paid it once per
forked child just to read a few string constants (UN-4136).

``executor/tasks.py`` is the production registration site: ``workers/worker.py``
exec-loads that file by path for both the Celery and PG executor roles.
``executor/worker.py`` calls it too, for the separate Celery app it builds,
which today only the tests use. The call is idempotent and re-entrant, so the
order they run in does not matter.
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
    clears the registry; tests that do re-register explicitly (see
    ``tests/test_legacy_executor_scaffold.py``).

    Idempotent, and safe to re-enter: a cloud plugin whose own import graph
    reaches this function during ``ep.load()`` will not restart discovery.

    Returns:
        The cloud executor entry point names — the same list on every call, not
        just the first. An empty list means no cloud plugins are installed,
        which is the OSS case.
    """
    global _cloud_executors

    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401

    if _cloud_executors is None:
        # Latch BEFORE discovering. ``ep.load()`` executes third-party code, and
        # a plugin that reaches back into this function would otherwise find the
        # latch still unset and restart the entry point loop, nesting once per
        # level. The import-side-effect version this replaced got that safety
        # free from ``sys.modules``.
        _cloud_executors = []
        from executor.executors.plugins.loader import ExecutorPluginLoader

        try:
            _cloud_executors = ExecutorPluginLoader.discover_executors()
        except BaseException:
            # Leave discovery un-run rather than latched-but-empty, so a caller
            # that survives the failure retries instead of silently getting a
            # permanently empty list.
            _cloud_executors = None
            raise

    return _cloud_executors


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

    Only discovery: the bundled executor is re-registered by
    :func:`register_all` itself whenever the registry has lost it, so this does
    not need to — and cannot — evict it from ``sys.modules``.
    """
    global _cloud_executors
    _cloud_executors = None


__all__ = ["LegacyExecutor", "register_all"]
