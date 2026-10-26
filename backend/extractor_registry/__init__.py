"""Shared Extractor Agent registry (UN-4214).

One catalogue, two front doors. See ``spec.py`` for the design and why the
dispatched operation and the agent's name are per-door columns.

Consumers:

* ``pluggable_apps.agentic_studio_v1.extractor_agents`` re-exports the
  Studio-facing names from here, so every existing import site keeps working.
* ``agent_kv.constants`` derives ``EXTRACTOR_ROUTES`` from ``api_routes()``.
"""

from extractor_registry.catalogue import (
    EXECUTOR_AGENTIC,
    EXECUTOR_AGENTIC_KV,
    EXECUTOR_AGENTIC_TABLE,
    EXTRACTOR_AGENTS,
    api_agent,
    api_routes,
    default_primary_key,
    get_agent,
    primary_agents,
    specialized_agents,
)
from extractor_registry.spec import (
    ExtractorAgentKey,
    ExtractorAgentKind,
    ExtractorAgentSpec,
)

__all__ = [
    "EXECUTOR_AGENTIC",
    "EXECUTOR_AGENTIC_KV",
    "EXECUTOR_AGENTIC_TABLE",
    "EXTRACTOR_AGENTS",
    "ExtractorAgentKey",
    "ExtractorAgentKind",
    "ExtractorAgentSpec",
    "api_agent",
    "api_routes",
    "default_primary_key",
    "get_agent",
    "primary_agents",
    "specialized_agents",
]
