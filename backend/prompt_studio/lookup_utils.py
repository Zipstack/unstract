"""Shared utility for lookup config resolution.

Wraps the cloud-only build_lookup_config_for_prompt call so that
OSS callers don't repeat the try/except ImportError guard.
"""

import logging

logger = logging.getLogger(__name__)


def get_lookup_config(prompt) -> dict | None:
    """Return lookup config for a prompt, or None if lookups are unavailable.

    This is a thin wrapper around the cloud plugin's
    build_lookup_config_for_prompt. In OSS deployments where the plugin
    is absent, it returns None silently.
    """
    try:
        from pluggable_apps.lookup_v1.execution import (
            build_lookup_config_for_prompt,
        )

        return build_lookup_config_for_prompt(prompt)
    except ImportError:
        return None
