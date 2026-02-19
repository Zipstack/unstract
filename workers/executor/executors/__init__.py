"""Executor implementations package.

Importing this module triggers ``@ExecutorRegistry.register`` for all
bundled executors.
"""

from executor.executors.legacy_executor import LegacyExecutor

__all__ = ["LegacyExecutor"]
