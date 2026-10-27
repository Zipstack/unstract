"""The shared Extractor Agent catalogue (UN-4214).

`SimpleTestCase` throughout: the catalogue is a frozen-dataclass table with no
DB access, so these belong in the `unit-backend` tier (see
`backend/conftest.py`, which infers the tier from the base class).
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from extractor_registry import (
    EXTRACTOR_AGENTS,
    ExtractorAgentKey,
    ExtractorAgentKind,
    ExtractorAgentSpec,
    api_agent,
    api_routes,
    default_primary_key,
    get_agent,
    primary_agents,
    specialized_agents,
)


class ApiRoutesEnforcesAvailabilityTest(SimpleTestCase):
    """`api_routes()` is the blind API's admission gate, not a convenience view.

    `SUPPORTED_EXTRACTORS` in `agent_kv.execution_serializers` is
    `tuple(EXTRACTOR_ROUTES)`, which is now `tuple(api_routes())`. So whether a
    row appears here decides whether a submit gets a 400 at the serializer or a
    202 onto a queue that may have no consumer. That is the whole reason the
    old hand-written table omitted `kv` rather than marking it somehow.
    """

    def test_an_unavailable_agent_is_omitted(self) -> None:
        routes = api_routes()
        self.assertNotIn("kv", routes)
        # ...and the reason is availability, not a missing API door: the row
        # declares both halves of its door, so omission can only come from the
        # flag. Without this, the test would still pass if someone deleted the
        # api_extractor/api_operation instead.
        kv = get_agent(ExtractorAgentKey.MULTI_STAGE)
        self.assertEqual(kv.api_extractor, "kv")
        self.assertEqual(kv.api_operation, "kv_extract")
        self.assertFalse(kv.available)

    def test_flipping_available_adds_the_route(self) -> None:
        """The inverse, so the omission above is attributable to the flag.

        Also the documented re-enable procedure: one line, one place. If this
        ever fails, `available=True` no longer re-enables an extractor and the
        comment in `agent_kv.constants` is lying.
        """
        kv = get_agent(ExtractorAgentKey.MULTI_STAGE)
        with patch.dict(
            EXTRACTOR_AGENTS,
            {ExtractorAgentKey.MULTI_STAGE: ExtractorAgentSpec(
                **{**kv.__dict__, "available": True}
            )},
        ):
            routes = api_routes()
        self.assertEqual(routes["kv"], ("agentic_kv", "kv_extract"))

    def test_an_agent_with_no_api_door_never_appears(self) -> None:
        """`simple` is Studio-only; the blind API exposes `kv` and `table`."""
        self.assertNotIn("simple", api_routes())
        simple = get_agent(ExtractorAgentKey.SIMPLE)
        self.assertTrue(simple.available, "simple IS deployed")
        self.assertIsNone(simple.api_operation, "it just has no API door")

    def test_routes_are_rebuilt_per_call(self) -> None:
        """Not frozen at import, or the patch-based tests above would be lying."""
        before = api_routes()
        with patch.dict(EXTRACTOR_AGENTS, {}, clear=True):
            self.assertEqual(api_routes(), {})
        self.assertEqual(api_routes(), before)


class PerDoorColumnsTest(SimpleTestCase):
    """The divergence that made two registries grow in the first place."""

    def test_the_table_agent_dispatches_a_different_operation_per_door(self) -> None:
        """One executor, two operations with different required parameters.

        `table_extract` resolves LLM/OCR adapters from stored configuration;
        `table_extract_api` takes them in the request. Collapsing these into a
        single `operation` field is what this module exists to prevent, so it
        is pinned rather than left as a comment.
        """
        table = get_agent(ExtractorAgentKey.TABLE)
        self.assertEqual(table.ide_operation, "table_extract")
        self.assertEqual(table.api_operation, "table_extract_api")
        self.assertNotEqual(table.ide_operation, table.api_operation)
        # Same executor either way -- the blind API deliberately reuses the
        # already-wired celery_executor_agentic_table queue.
        self.assertEqual(table.executor, "agentic_table")

    def test_the_two_doors_name_the_kv_engine_differently(self) -> None:
        """Studio `multi_stage` vs API `kv`; both are wire format for their door."""
        kv = get_agent(ExtractorAgentKey.MULTI_STAGE)
        self.assertEqual(kv.key, "multi_stage")
        self.assertEqual(kv.api_extractor, "kv")
        self.assertEqual(api_agent("kv").key, ExtractorAgentKey.MULTI_STAGE)

    def test_api_agent_resolves_a_withdrawn_extractor(self) -> None:
        """Lookup must not filter on availability.

        A job row records the extractor that ran. If `api_agent` hid
        unavailable agents, a status read for an in-flight or historical `kv`
        job would stop describing it the moment the agent was withdrawn.
        """
        self.assertIsNotNone(api_agent("kv"))
        self.assertNotIn("kv", api_routes())

    def test_a_half_declared_api_door_is_refused(self) -> None:
        """Both halves or neither -- one alone fails invisibly until a submit."""
        base = dict(
            key="x", name="X", kind=ExtractorAgentKind.PRIMARY,
            executor="e", ide_operation="o",
        )
        with self.assertRaises(ValueError):
            ExtractorAgentSpec(**base, api_operation="op")
        with self.assertRaises(ValueError):
            ExtractorAgentSpec(**base, api_extractor="name")
        # Neither is fine: that is the Studio-only shape.
        self.assertIsNone(ExtractorAgentSpec(**base).api_operation)


class CatalogueShapeTest(SimpleTestCase):
    """Invariants the Studio's binding relies on."""

    def test_keys_match_the_enum(self) -> None:
        self.assertEqual(set(EXTRACTOR_AGENTS), set(ExtractorAgentKey.values))

    def test_each_row_is_keyed_by_its_own_key(self) -> None:
        for key, spec in EXTRACTOR_AGENTS.items():
            self.assertEqual(key, spec.key)

    def test_exactly_one_default_primary(self) -> None:
        defaults = [s for s in primary_agents() if s.is_default]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(default_primary_key(), defaults[0].key)

    def test_the_default_primary_is_available(self) -> None:
        """A new profile must not be born pointing at an agent that cannot run."""
        self.assertTrue(get_agent(default_primary_key()).available)

    def test_specialized_agents_carry_a_placeholder(self) -> None:
        """Their output is substituted into the schema; without a token it cannot be."""
        for spec in specialized_agents():
            self.assertIsNotNone(spec.schema_placeholder, spec.key)

    def test_primary_agents_carry_no_placeholder(self) -> None:
        for spec in primary_agents():
            self.assertIsNone(spec.schema_placeholder, spec.key)

    def test_every_kind_is_one_of_the_two(self) -> None:
        for spec in EXTRACTOR_AGENTS.values():
            self.assertIn(spec.kind, set(ExtractorAgentKind.values), spec.key)

    def test_api_extractor_names_are_unique(self) -> None:
        """`api_agent` scans linearly and returns the first match."""
        names = [s.api_extractor for s in EXTRACTOR_AGENTS.values() if s.api_extractor]
        self.assertEqual(len(names), len(set(names)))

class EnumValuesArePersistedLiteralsTest(SimpleTestCase):
    """The enum VALUES are database content, so pin them, not just their shape.

    These strings are what ``agentic_extractor_agent_config.agent_key`` and
    ``.kind`` physically hold, and they are frozen a second time as literal
    tuples in that app's migration ``0009_extraction_profiles`` (``_KIND_CHOICES``
    / ``_KEY_CHOICES``) -- in the CLOUD repository, which this repository's CI
    never checks out. So an edit here that renames a value cannot be caught by
    anything on this side unless it is caught here.

    It would not be caught on the other side either, and this is measured, not
    assumed: renaming ``SIMPLE`` to ``"simple_x"`` and ``SPECIALIZED`` to
    ``"specialized_x"`` left the whole 447-test unit tier of both repositories
    green. The consequence is silent -- ``get_agent("simple")`` returns None for
    every row already written, so every saved profile raises "Unknown Primary
    Extractor Agent", and ``kind``-filtered queries stop matching, which makes
    an existing profile look like it has no primary agent at all.

    The sibling tests here deliberately do NOT cover this: they compare
    ``EXTRACTOR_AGENTS`` against ``ExtractorAgentKey.values``, and both sides
    move together under a rename, so they are self-referential for this
    purpose. Asserting the literals is the only form that fails.
    """

    def test_agent_key_values_are_the_persisted_literals(self) -> None:
        self.assertEqual(
            set(ExtractorAgentKey.values), {"simple", "multi_stage", "table"}
        )

    def test_agent_kind_values_are_the_persisted_literals(self) -> None:
        self.assertEqual(set(ExtractorAgentKind.values), {"primary", "specialized"})
