"""Executor implementations package.

Registration is **explicit**: call :func:`register_all` to import the bundled
executors and discover cloud ones via entry points. It used to run as a side
effect of importing this package, which meant that importing *any* submodule —
including ``executor.executors.constants``, which itself imports nothing but
``enum`` — dragged in ``LegacyExecutor`` and the entire adapter stack behind it.

That cost ~9s, and the file_processing worker paid it once per forked child just
to read a few string constants (UN-4136). Keeping registration in a function
lets a consumer import the cheap submodules without booting the executor.

The two entrypoints that need a populated registry — ``executor/worker.py``
(Celery) and ``executor/tasks.py`` (the PG executor consumer) — call this
directly. It is idempotent, so both calling it is harmless.
"""

_registered = False


def register_all() -> list[str]:
    """Populate ``ExecutorRegistry`` with the bundled and cloud executors.

    Importing ``LegacyExecutor`` runs its ``@ExecutorRegistry.register``
    decorator; ``discover_executors()`` does the same for each cloud executor
    installed under the ``unstract.executor.executors`` entry point group.

    Returns:
        The cloud executor entry point names discovered on this call, and on a
        repeat call the empty list (the registry is already populated).
    """
    global _registered
    if _registered:
        return []
    from executor.executors.legacy_executor import LegacyExecutor  # noqa: F401
    from executor.executors.plugins.loader import ExecutorPluginLoader

    # If no cloud plugins are installed this returns an empty list.
    cloud_executors = ExecutorPluginLoader.discover_executors()
    _registered = True
    return cloud_executors


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


def _reset_for_tests() -> None:
    """Clear the idempotency latch so a test can re-run discovery."""
    global _registered
    _registered = False


__all__ = ["LegacyExecutor", "register_all"]
