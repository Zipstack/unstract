"""Plugin system for Unstract.

This module provides the core plugin infrastructure for loading and managing
enterprise plugins that are injected at build time from the cloud repository.

The PluginManager supports framework-agnostic plugin loading with Flask and
Django-specific wrappers available in unstract.core.flask and unstract.core.django.
"""

from .plugin_manager import PluginManager

__all__ = ["PluginManager"]
