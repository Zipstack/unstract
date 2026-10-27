"""Shared Extractor Agent registry (UN-4214).

One catalogue, two front doors. See ``spec.py`` for the design and why the
dispatched operation and the agent's name are per-door columns.

Consumers:

* The Studio (``pluggable_apps.agentic_studio_v1``, cloud-only) imports from
  here directly, at eleven sites across its serializers, views, services,
  models and tests. There is deliberately NO compatibility façade: the app's
  own ``extractor_agents`` package was deleted rather than shimmed, because a
  shim would have let a stale import survive and quietly reintroduce a second
  catalogue, which is the condition this package exists to remove.
  ``agentic_studio_v1.models.enums`` re-exports the two ``TextChoices`` only
  because that module is the Studio's single entry point for them -- five
  non-test sites import them from there, including the ``choices=`` on its
  model fields.
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
