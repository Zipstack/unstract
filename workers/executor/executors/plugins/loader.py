"""Entry-point-based discovery for cloud plugins and executors.

Two entry point groups are used:

- ``unstract.executor.plugins``
    Utility plugins (highlight-data, challenge, evaluation).
    Loaded lazily on first ``get()`` call and cached.

- ``unstract.executor.executors``
    Executor classes that self-register via ``@ExecutorRegistry.register``.
    Loaded eagerly at worker startup from ``executors/__init__.py``.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ExecutorPluginLoader:
    """Discovers cloud plugins and executors via setuptools entry points."""

    _plugins: dict[str, type] | None = None

    @classmethod
    def get(cls, name: str) -> type | None:
        """Get a plugin class by name.  Returns None if not installed."""
        if cls._plugins is None:
            cls._discover_plugins()
        return cls._plugins.get(name)

    @classmethod
    def discover_executors(cls) -> list[str]:
        """Load cloud executor classes via entry points.

        Importing each entry point's class triggers
        ``@ExecutorRegistry.register``.  Called once at worker startup.

        Returns:
            List of discovered executor entry point names.
        """
        from importlib.metadata import entry_points

        discovered: list[str] = []
        eps = entry_points(group="unstract.executor.executors")
        for ep in eps:
            try:
                ep.load()  # import triggers @ExecutorRegistry.register
                discovered.append(ep.name)
                logger.info("Loaded cloud executor: %s", ep.name)
            except Exception:
                logger.warning(
                    "Failed to load cloud executor: %s",
                    ep.name,
                    exc_info=True,
                )
        return discovered

    @classmethod
    def _discover_plugins(cls) -> None:
        """Discover utility plugins from entry points (lazy, first use)."""
        from importlib.metadata import entry_points

        cls._plugins = {}
        eps = entry_points(group="unstract.executor.plugins")
        for ep in eps:
            try:
                cls._plugins[ep.name] = ep.load()
                logger.info("Loaded executor plugin: %s", ep.name)
            except Exception:
                logger.warning(
                    "Failed to load executor plugin: %s",
                    ep.name,
                    exc_info=True,
                )

    @classmethod
    def clear(cls) -> None:
        """Reset cached state.  Intended for tests only."""
        cls._plugins = None
