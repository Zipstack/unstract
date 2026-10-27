"""The shared Extractor Agent catalogue (UN-4214, architecture review §6.2).

There are TWO front doors onto the same executor plugins:

* **Agentic Prompt Studio** picks an agent per ``ExtractionProfile`` row and
  dispatches the plugin's *IDE* operation, which resolves its LLM and OCR
  adapters from stored configuration.
* **The Agent-KV blind API** picks an extractor from request-scoped options and
  dispatches the plugin's *API* operation, which takes its adapters in the
  request.

WHY THE OPERATION IS PER-DOOR, not per-agent: ``agentic_table`` registers two
distinct operations with different required parameters — ``table_extract`` for
the IDE and ``table_extract_api`` for the blind API — so the operation belongs
to the binding. The agent's NAME diverges too: the Studio calls the KV engine
``multi_stage`` where the API calls it ``kv``. Both are per-door columns on one
row so a single ``operation`` field cannot be reintroduced by accident.

This package lives in the OSS tree deliberately. ``pluggable_apps`` is
cloud-only, so a registry living there cannot be imported by
``agent_kv`` — which ships in OSS. The dependency only runs one way.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models


class ExtractorAgentKind(models.TextChoices):
    """Kind of Extractor Agent within an Extraction Profile.

    A profile has exactly one PRIMARY agent (mandatory) and zero or more
    SPECIALIZED agents that run in relation to it.
    """

    PRIMARY = "primary", "Primary Extractor Agent"
    SPECIALIZED = "specialized", "Specialized Extraction Agent"


class ExtractorAgentKey(models.TextChoices):
    """Stable keys for the Extractor Agents shipped at launch.

    These are the STUDIO-side identifiers, stored on
    ``ExtractorAgentConfig.agent_key``. The blind API's own names for the same
    engines are ``ExtractorAgentSpec.api_extractor``, which differ — see the
    module docstring.
    """

    SIMPLE = "simple", "Simple Extractor"
    MULTI_STAGE = "multi_stage", "Multi-Stage Extractor"
    TABLE = "table", "Table Extractor"


@dataclass(frozen=True)
class ExtractorAgentSpec:
    """Static description of an Extractor Agent, shared by both front doors.

    Attributes:
        key: Stable Studio identifier, stored on
            ``ExtractorAgentConfig.agent_key``.
        name: Human-readable label for the UI.
        kind: PRIMARY (one per profile, mandatory) or SPECIALIZED (optional,
            addable once each).
        executor: Worker executor that runs this agent (e.g. ``"agentic"`` or
            ``"agentic_table"``). Shared by both doors — the executor is the
            same process either way. Whether this executor's derived
            ``celery_executor_<executor>`` queue has a consumer is a separate
            fact, per row: ``agentic_table``'s does, ``agentic_kv``'s
            deliberately does not (see ``available`` below).
        ide_operation: Operation the STUDIO dispatches. Resolves adapters from
            stored configuration.
        api_operation: Operation the BLIND API dispatches, or ``None`` where
            the agent has no blind-API door at all (the Simple extractor has
            none). Takes its adapters in the request, and its required
            parameters differ from the IDE operation's.
        api_extractor: The blind API's own name for this agent, or ``None``
            where it has no API door. Deliberately separate from ``key``:
            the API calls the KV engine ``kv`` where the Studio calls it
            ``multi_stage``, and changing either is a wire-format break for
            that door.
        supports_multimodal: Whether this agent's engine accepts multi-modal
            (text + image) input at all.
        multimodal_required: And the Studio offers no toggle, because it cannot
            be turned off -- true for the Table Extractor. Implies
            ``supports_multimodal``; ``__post_init__`` enforces it.
            CONFIGURATION SURFACE ONLY: no dispatch path on either door reads
            either flag, or the ``is_multimodal`` column they govern.
        schema_placeholder: For Specialized agents, the token in the schema
            that this agent's output is substituted into at runtime; ``None``
            for Primary agents.
        output_key: Key holding the useful value inside this agent's result
            envelope -- the Table executor returns ``{"tables": [...],
            "page_count": ..., ...}`` and only ``tables`` belongs at the
            placeholder. ``None`` means the whole result is the value.
        is_default: Whether this is the default Primary agent for new profiles.
        requires_target_table: Whether the agent needs a ``target_table`` hint
            in ``ExtractorAgentConfig.agent_settings`` -- true for the Table
            Extractor, whose engine cannot run without one.
        available: Whether the agent's executor is deployed. Necessary but
            NOT sufficient at either door: ``api_routes()`` also requires
            ``api_operation`` and ``api_extractor``, and the Studio also
            requires a parameter builder, which lives in the cloud tree where
            OSS CI cannot see it. Flipping this True without the matching
            cloud-side builder is the mistake it guards -- see
            ``agentic_studio_v1.services.agent_dispatch.is_dispatchable``,
            which cloud PR #1894 adds (it is not on cloud main yet).
    """

    key: str
    name: str
    kind: str
    executor: str
    ide_operation: str
    api_operation: str | None = None
    api_extractor: str | None = None
    supports_multimodal: bool = False
    multimodal_required: bool = False
    schema_placeholder: str | None = None
    output_key: str | None = None
    is_default: bool = False
    requires_target_table: bool = False
    available: bool = True

    def __post_init__(self) -> None:
        """Reject half-declared shapes.

        ``api_operation`` and ``api_extractor`` are meaningless apart: a route
        needs both a name to be requested by and an operation to dispatch.
        Either half alone drops the agent out of ``api_routes()`` silently --
        its filter requires both -- and that silence lasts until a submit
        lands.
        """
        if self.multimodal_required and not self.supports_multimodal:
            raise ValueError(f"{self.key}: multimodal_required needs supports_multimodal")
        if bool(self.api_operation) != bool(self.api_extractor):
            raise ValueError(
                f"{self.key}: api_operation and api_extractor must be set "
                f"together or both omitted (got api_operation="
                f"{self.api_operation!r}, api_extractor={self.api_extractor!r})"
            )
