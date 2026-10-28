"""The one Extractor Agent catalogue, and each front door's view of it.

See ``spec.py`` for why the operation and the agent's name are per-door
columns rather than single fields.

"Both front doors" means both BACKEND doors, and that is a consequence of
where this package sits rather than a necessity. The worker tier cannot import
it, so it keeps its own copies of these literals -- including in production
code (``workers/executor/tasks.py``'s billing gate), where the agreement is
held only by a test that parses that file as text.

OPEN QUESTION, deliberately recorded rather than answered: ``unstract/core`` is
Django-free, is already an editable dependency of both ``backend`` and
``workers``, and already hosts a shared enum moved there for this exact reason
(see ``workers/shared/enums.py``'s note on ``AuthorizationType``). Only the two
``TextChoices`` classes here need Django. That is plausibly the better home and
would let the worker tier derive rather than copy; it was not chosen, and the
choice has not been argued either way. Decide it before a second package
copies this pattern.

Per-field test coverage of the cross-tier agreement is uneven and worth knowing
before relying on it: ``agent_kv/tests/test_queue_wiring_is_derived.py`` covers
``executor`` and ``api_operation``, ``tests/test_cross_repo_output_key.py``
covers ``output_key`` from this side only, and ``ide_operation`` is covered by
nothing.
"""

from __future__ import annotations

from extractor_registry.spec import (
    ExtractorAgentKey,
    ExtractorAgentKind,
    ExtractorAgentSpec,
)

#: Executor plugin names. The blind API reuses the IDE's executor for the table
#: path on purpose: a second executor name would derive a second
#: ``celery_executor_<name>`` queue, and an unwired queue accepts work and
#: drains nothing, silently. No count of the wiring sites here -- two reviewers
#: counted them independently and got different answers from equally
#: defensible sets, which is the argument against stating one.
EXECUTOR_AGENTIC = "agentic"
EXECUTOR_AGENTIC_KV = "agentic_kv"
EXECUTOR_AGENTIC_TABLE = "agentic_table"

EXTRACTOR_AGENTS: dict[str, ExtractorAgentSpec] = {
    ExtractorAgentKey.SIMPLE: ExtractorAgentSpec(
        key=ExtractorAgentKey.SIMPLE,
        name="Simple Extractor",
        kind=ExtractorAgentKind.PRIMARY,
        executor=EXECUTOR_AGENTIC,
        ide_operation="agentic_extract",
        # No blind-API door at all. The API's namespace declares `kv` and
        # `table`; only `table` is routable today. Declared as None rather than
        # omitted from the catalogue, because the Studio does offer this agent
        # and `api_routes()` is what decides API exposure.
        api_operation=None,
        api_extractor=None,
        supports_multimodal=True,
        is_default=True,
    ),
    ExtractorAgentKey.MULTI_STAGE: ExtractorAgentSpec(
        key=ExtractorAgentKey.MULTI_STAGE,
        name="Multi-Stage Extractor",
        kind=ExtractorAgentKind.PRIMARY,
        executor=EXECUTOR_AGENTIC_KV,
        # The KV engine is the one agent whose two doors agree on the
        # operation; both dispatch `kv_extract`. Still modelled as two columns,
        # because agreeing today is not the same as being one field.
        ide_operation="kv_extract",
        api_operation="kv_extract",
        api_extractor="kv",
        # Multi-modality is a checkbox on both Primary agents.
        supports_multimodal=True,
        # NOT DEPLOYED: `workers/plugins/agentic_kv` is on no main branch in
        # either repo, so neither door may run it. Flipping this True without
        # the plugin accepts a submit with a 202 onto a queue with no consumer.
        # Not sufficient on its own either -- see `available` in `spec.py`.
        available=False,
    ),
    ExtractorAgentKey.TABLE: ExtractorAgentSpec(
        key=ExtractorAgentKey.TABLE,
        name="Table Extractor",
        kind=ExtractorAgentKind.SPECIALIZED,
        executor=EXECUTOR_AGENTIC_TABLE,
        # THE DIVERGENCE THIS MODULE EXISTS FOR. One executor, two operations
        # with different required parameters: the IDE operation resolves its
        # LLM and OCR adapters from stored configuration, the API operation
        # takes them in the request and refuses without specific roles.
        ide_operation="table_extract",
        api_operation="table_extract_api",
        api_extractor="table",
        supports_multimodal=True,
        multimodal_required=True,
        requires_target_table=True,
        schema_placeholder="{{TABLE_EXTRACTOR_AGENT_OUTPUT}}",
        # ExtractionOutput.to_dict() wraps the rows in run metadata, so the
        # rows are unwrapped by this key rather than substituted whole. The
        # key is locked against the producer in tests/test_cross_repo_*.py.
        output_key="tables",
    ),
}


def get_agent(key: str) -> ExtractorAgentSpec | None:
    """Return the spec for a STUDIO ``key``, or ``None`` if unknown."""
    return EXTRACTOR_AGENTS.get(key)


def primary_agents() -> list[ExtractorAgentSpec]:
    """All Primary Extractor Agents (mutually exclusive per profile)."""
    return [
        spec
        for spec in EXTRACTOR_AGENTS.values()
        if spec.kind == ExtractorAgentKind.PRIMARY
    ]


def specialized_agents() -> list[ExtractorAgentSpec]:
    """All Specialized Extraction Agents (optional add-ons)."""
    return [
        spec
        for spec in EXTRACTOR_AGENTS.values()
        if spec.kind == ExtractorAgentKind.SPECIALIZED
    ]


def default_primary_key() -> str:
    """Key of the default Primary agent used for new/backfilled profiles.

    The return value is PERSISTED as ``ExtractorAgentConfig.agent_key`` and the
    cloud profile writer does not re-check availability, so this must never
    return an agent that cannot run.

    Neither branch below checks ``available`` on the flagged row, and does not
    need to: ``ExtractorAgentSpec.__post_init__`` refuses
    ``is_default`` without ``available``, so a flagged-but-undeployed row
    cannot exist to be found. The fallback's check is not redundant with that
    -- it covers the different case where NO row is flagged.
    """
    for spec in primary_agents():
        if spec.is_default:
            return spec.key
    # No flag set. Fall back to the first AVAILABLE Primary rather than the
    # first Primary: insertion order is not an availability guarantee.
    for spec in primary_agents():
        if spec.available:
            return spec.key
    raise ValueError(
        "No Primary extractor agent is available; a profile cannot be given a "
        "default that cannot run."
    )


def api_routes() -> dict[str, tuple[str, str]]:
    """The blind API's view: ``{extractor_name: (executor, api_operation)}``.

    AVAILABILITY IS ENFORCED HERE, and this is the function's main job. Only
    agents that are both deployed (``available``) and have an API door appear,
    so an undeployed extractor is absent from the mapping exactly as it was
    when the API kept its own hand-maintained table. That absence is what
    turns a submit for it into a 400 at the serializer, because
    ``SUPPORTED_EXTRACTORS`` is derived from these keys — rather than a 202
    onto a queue nothing drains.

    Built fresh on each call rather than computed once at import, so a test may
    patch ``EXTRACTOR_AGENTS`` and see the derived view change with it.

    ``api_extractor`` must be unique across rows, and this raises when it is
    not. A dict comprehension here is last-wins while ``api_agent`` is
    first-match, so a duplicate would have the two views disagree about one
    live wire name -- dispatching to one row and describing another. Checked
    here rather than only in a test, because a test covers the shipped
    catalogue and this covers any catalogue a caller patches in.
    """
    doors = [
        spec
        for spec in EXTRACTOR_AGENTS.values()
        if spec.available and spec.api_operation and spec.api_extractor
    ]
    names = [spec.api_extractor for spec in doors]
    if len(names) != len(set(names)):
        raise ValueError(
            f"api_extractor names must be unique across rows; got {sorted(names)}"
        )
    return {spec.api_extractor: (spec.executor, spec.api_operation) for spec in doors}


def api_agent(extractor: str | None) -> ExtractorAgentSpec | None:
    """Return the spec behind a blind-API ``extractor`` name, or ``None``.

    Resolves the API's namespace rather than the Studio's — ``"kv"`` finds the
    agent the Studio knows as ``multi_stage``. Does NOT filter on availability,
    so a withdrawn agent still resolves; callers that need routability use
    ``api_routes()``.

    NO CALLER YET. ``agent_kv``'s status path does not route through this, so
    nothing outside the tests depends on the non-filtering behaviour. Wire it
    or delete it; do not assume it is already load-bearing.
    """
    # Guard the falsy case before comparing: `simple` declares
    # `api_extractor=None`, so a bare `== extractor` matches None == None and
    # hands the caller the one agent with no API door.
    if not extractor:
        return None
    for spec in EXTRACTOR_AGENTS.values():
        if spec.api_extractor == extractor:
            return spec
    return None
