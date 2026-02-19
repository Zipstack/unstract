"""Executor registry for the pluggable executor framework.

Provides a simple in-process registry where executor classes
self-register at import time via the ``@ExecutorRegistry.register``
decorator.  The executor worker imports all executor modules so
that registration happens before any task is processed.
"""

import logging
from typing import TypeVar

from unstract.sdk1.execution.executor import BaseExecutor

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=type[BaseExecutor])


class ExecutorRegistry:
    """In-process registry mapping executor names to classes.

    Usage::

        @ExecutorRegistry.register
        class LegacyExecutor(BaseExecutor):
            @property
            def name(self) -> str:
                return "legacy"
            ...

        executor = ExecutorRegistry.get("legacy")
    """

    _registry: dict[str, type[BaseExecutor]] = {}

    @classmethod
    def register(cls, executor_cls: T) -> T:
        """Class decorator that registers an executor.

        Instantiates the class once to read its ``name`` property,
        then stores the *class* (not the instance) so a fresh
        instance is created per ``get()`` call.

        Args:
            executor_cls: A concrete ``BaseExecutor`` subclass.

        Returns:
            The same class, unmodified (passthrough decorator).

        Raises:
            TypeError: If *executor_cls* is not a BaseExecutor
                subclass.
            ValueError: If an executor with the same name is
                already registered.
        """
        if not (
            isinstance(executor_cls, type)
            and issubclass(executor_cls, BaseExecutor)
        ):
            raise TypeError(
                f"{executor_cls!r} is not a BaseExecutor subclass"
            )

        # Instantiate temporarily to read the name property
        instance = executor_cls()
        name = instance.name

        if name in cls._registry:
            existing = cls._registry[name]
            raise ValueError(
                f"Executor name {name!r} is already registered "
                f"by {existing.__name__}; cannot register "
                f"{executor_cls.__name__}"
            )

        cls._registry[name] = executor_cls
        logger.info(
            "Registered executor %r (%s)",
            name,
            executor_cls.__name__,
        )
        return executor_cls

    @classmethod
    def get(cls, name: str) -> BaseExecutor:
        """Look up and instantiate an executor by name.

        Args:
            name: The executor name (e.g. ``"legacy"``).

        Returns:
            A fresh ``BaseExecutor`` instance.

        Raises:
            KeyError: If no executor is registered under *name*.
        """
        executor_cls = cls._registry.get(name)
        if executor_cls is None:
            available = ", ".join(sorted(cls._registry)) or "(none)"
            raise KeyError(
                f"No executor registered with name {name!r}. "
                f"Available: {available}"
            )
        return executor_cls()

    @classmethod
    def list_executors(cls) -> list[str]:
        """Return sorted list of registered executor names."""
        return sorted(cls._registry)

    @classmethod
    def clear(cls) -> None:
        """Remove all registered executors (for testing)."""
        cls._registry.clear()
