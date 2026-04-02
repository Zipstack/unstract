"""Executor implementations package.

Importing this module triggers ``@ExecutorRegistry.register`` for all
bundled executors and discovers cloud executors via entry points.
"""

from executor.executors.legacy_executor import LegacyExecutor
from executor.executors.plugins.loader import ExecutorPluginLoader

# Discover and register cloud executors installed via entry points.
# Each cloud executor class is decorated with @ExecutorRegistry.register,
# so importing it (via ep.load()) is enough to register it.
# If no cloud plugins are installed this returns an empty list.
_cloud_executors = ExecutorPluginLoader.discover_executors()

__all__ = ["LegacyExecutor"]
