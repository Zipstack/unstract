"""Shared Extractor Agent registry (UN-4214).

One catalogue, two front doors. See ``spec.py`` for the design and why the
dispatched operation and the agent's name are per-door columns.

Consumers:

* The Studio (``pluggable_apps.agentic_studio_v1``, cloud-only) imports from
  here directly **as of cloud PR #1894**, which also deletes its own
  ``extractor_agents`` package rather than shimming it, so a stale import
  cannot quietly reintroduce a second catalogue, and re-exports the two
  ``TextChoices`` from ``agentic_studio_v1.models.enums``. None of that is on
  cloud main yet; this package merges first.
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
