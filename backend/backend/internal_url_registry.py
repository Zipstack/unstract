"""Internal URL Registry System

This registry system allows dynamic loading of internal URLs based on settings
configuration, similar to how Django apps are loaded. This provides clean
separation between OSS and cloud features without explicit imports.

Architecture:
- OSS: Only base internal URLs are registered
- Cloud: Additional cloud URLs are registered via settings
- No try/except imports needed - everything is settings-driven
"""

import importlib
import logging
from typing import Any

from django.urls import include, path

logger = logging.getLogger(__name__)


class InternalURLRegistry:
    """Registry for managing internal API URLs dynamically."""

    def __init__(self):
        self._url_patterns: list[Any] = []
        self._registered_modules: dict[str, str] = {}
        self._initialized = False

    def register_url_module(
        self, name: str, url_path: str, module_path: str, enabled: bool = True
    ) -> None:
        """Register a URL module to be included in internal URLs.

        Args:
            name: Unique name for this URL module
            url_path: URL path prefix (e.g., "manual-review/internal/")
            module_path: Python module path (e.g., "pluggable_apps.manual_review_v2.internal_urls")
            enabled: Whether this module should be loaded
        """
        if not enabled:
            logger.debug(f"URL module '{name}' disabled, skipping registration")
            return

        if name in self._registered_modules:
            logger.warning(f"URL module '{name}' already registered, skipping")
            return

        try:
            # Create URL pattern
            url_pattern = path(url_path, include(module_path), name=f"internal_{name}")
            self._url_patterns.append(url_pattern)
            self._registered_modules[name] = module_path
            logger.info(f"Registered internal URL module: {name} -> {url_path}")

        except Exception as e:
            logger.error(f"Failed to register URL module '{name}': {e}")

    def get_url_patterns(self) -> list[Any]:
        """Get all registered URL patterns."""
        return self._url_patterns.copy()

    def is_registered(self, name: str) -> bool:
        """Check if a URL module is registered."""
        return name in self._registered_modules

    def get_registered_modules(self) -> dict[str, str]:
        """Get all registered modules."""
        return self._registered_modules.copy()

    def clear(self) -> None:
        """Clear all registered URLs (for testing)."""
        self._url_patterns.clear()
        self._registered_modules.clear()
        self._initialized = False


# Global registry instance
_internal_url_registry = InternalURLRegistry()


def register_internal_url(
    name: str, url_path: str, module_path: str, enabled: bool = True
) -> None:
    """Register an internal URL module.

    Args:
        name: Unique name for this URL module
        url_path: URL path prefix
        module_path: Python module path
        enabled: Whether this module should be loaded
    """
    _internal_url_registry.register_url_module(name, url_path, module_path, enabled)


def get_internal_url_patterns() -> list[Any]:
    """Get all registered internal URL patterns."""
    return _internal_url_registry.get_url_patterns()


def initialize_internal_urls_from_settings() -> None:
    """Initialize internal URLs based on Django settings.

    This function reads INTERNAL_URL_MODULES from settings and registers
    them with the registry. This allows cloud deployments to automatically
    include additional URLs without code changes.
    """
    from django.conf import settings

    if _internal_url_registry._initialized:
        return

    # Get internal URL modules from settings
    internal_url_modules = getattr(settings, "INTERNAL_URL_MODULES", {})

    logger.info(
        f"Initializing internal URLs from settings: {len(internal_url_modules)} modules"
    )

    for name, config in internal_url_modules.items():
        if isinstance(config, dict):
            # Full configuration
            url_path = config.get("url_path", f"{name}/")
            module_path = config.get("module_path")
            enabled = config.get("enabled", True)

            if module_path:
                register_internal_url(name, url_path, module_path, enabled)
            else:
                logger.warning(
                    f"No module_path specified for internal URL module: {name}"
                )

        elif isinstance(config, str):
            # Simple configuration - just module path
            register_internal_url(name, f"{name}/", config, True)

        else:
            logger.warning(f"Invalid configuration for internal URL module: {name}")

    _internal_url_registry._initialized = True

    registered_modules = _internal_url_registry.get_registered_modules()
    logger.info(
        f"Initialized {len(registered_modules)} internal URL modules: {list(registered_modules.keys())}"
    )


def get_internal_url_documentation() -> dict[str, Any]:
    """Get documentation for all registered internal URL modules."""
    registered_modules = _internal_url_registry.get_registered_modules()

    endpoints = {}
    for name, module_path in registered_modules.items():
        # Create endpoint documentation based on registered modules
        endpoints[f"{name}_base"] = f"/internal/{name}/"

        # Add specific endpoints based on known module types
        if "manual_review" in name:
            endpoints.update(
                {
                    f"{name}_queue": f"/internal/{name}/queue/",
                    f"{name}_rules": f"/internal/{name}/rules/",
                    f"{name}_settings": f"/internal/{name}/settings/",
                    f"{name}_workflows": f"/internal/{name}/workflows/",
                    f"{name}_auto_approval": f"/internal/{name}/auto-approval/",
                }
            )

    return endpoints


class CloudURLRegistry:
    """Registry for cloud-specific URLs that exist as separate files."""

    def __init__(self):
        self._cloud_patterns: list[Any] = []
        self._cloud_endpoints: dict[str, str] = {}
        self._cloud_modules: list[str] = [
            "backend.backend.cloud_internal_urls",  # Standard cloud internal URLs
            # Add other cloud module paths as needed
        ]
        self._initialized = False

    def initialize_cloud_urls(self) -> None:
        """Initialize cloud URLs by loading available cloud modules."""
        if self._initialized:
            return

        for module_path in self._cloud_modules:
            try:
                # Load the module dynamically without try/except imports in main code
                module = importlib.import_module(module_path)

                # Get URL patterns if available
                if hasattr(module, "get_cloud_url_patterns"):
                    patterns = module.get_cloud_url_patterns()
                    if patterns:
                        self._cloud_patterns.extend(patterns)
                        logger.info(
                            f"Loaded {len(patterns)} URL patterns from {module_path}"
                        )

                # Get endpoint documentation if available
                if hasattr(module, "get_cloud_url_documentation"):
                    endpoints = module.get_cloud_url_documentation()
                    if endpoints:
                        self._cloud_endpoints.update(endpoints)
                        logger.info(
                            f"Loaded {len(endpoints)} endpoint docs from {module_path}"
                        )

            except ImportError:
                # Module doesn't exist - this is fine, just means no cloud URLs
                logger.debug(f"Cloud module {module_path} not available (OSS deployment)")
            except Exception as e:
                logger.warning(f"Failed to load cloud module {module_path}: {e}")

        self._initialized = True

        if self._cloud_patterns:
            logger.info(
                f"Initialized cloud URLs: {len(self._cloud_patterns)} patterns, {len(self._cloud_endpoints)} endpoints"
            )

    def get_cloud_url_patterns(self) -> list[Any]:
        """Get cloud URL patterns."""
        self.initialize_cloud_urls()
        return self._cloud_patterns.copy()

    def get_cloud_url_documentation(self) -> dict[str, str]:
        """Get cloud URL documentation."""
        self.initialize_cloud_urls()
        return self._cloud_endpoints.copy()

    def clear(self) -> None:
        """Clear cloud URLs (for testing)."""
        self._cloud_patterns.clear()
        self._cloud_endpoints.clear()
        self._initialized = False


# Global cloud URL registry instance
_cloud_url_registry = CloudURLRegistry()


def get_cloud_url_patterns() -> list[Any]:
    """Get cloud URL patterns if available."""
    return _cloud_url_registry.get_cloud_url_patterns()


def get_cloud_url_documentation() -> dict[str, str]:
    """Get cloud URL documentation if available."""
    return _cloud_url_registry.get_cloud_url_documentation()
