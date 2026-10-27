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

        This pins the FLAG's effect on `api_routes()` and nothing more. It is
        deliberately not evidence for the re-enable procedure as a whole: a
        real flip also reds the guards that pin the omission (see
        `agent_kv.constants`), and it cannot reach `EXTRACTOR_ROUTES` at all,
        which is an import-time snapshot taken before any test body runs. The
        derivation itself is pinned in
        `agent_kv/tests/test_table_extractor_routing.py`.

        If `kv` is ever deliberately re-enabled this test does NOT go red --
        it patches `available=True` onto a row that is already True and
        becomes tautological, which is harder to notice than a failure. The
        assertion below is what makes that loud. Delete this test then, and
        say so, rather than leaving it passing for no reason.
        """
        kv = get_agent(ExtractorAgentKey.MULTI_STAGE)
        self.assertFalse(
            kv.available,
            "multi_stage is now available, so this test is tautological -- "
            "delete it rather than leaving it green.",
        )
        with patch.dict(
            EXTRACTOR_AGENTS,
            {ExtractorAgentKey.MULTI_STAGE: ExtractorAgentSpec(
                **{**kv.__dict__, "available": True}
            )},
        ):
            routes = api_routes()
        self.assertEqual(routes["kv"], ("agentic_kv", "kv_extract"))

    def test_an_agent_with_no_api_door_never_appears(self) -> None:
        """`simple` is Studio-only. The API's namespace declares `kv` and
        `table`; only `table` is routable today.

        Assert on the namespace `api_routes()` keys on -- its own
        `api_extractor` -- not on the Studio key. `assertNotIn("simple", ...)`
        could not fail under any implementation, because `simple` declares
        `api_extractor=None` and so is never a key of that mapping. (The Table
        row's key and api_extractor coincide; `simple`'s do not, which is why
        the old assertion was vacuous.)

        What this does NOT guard: dropping ONE half of `api_routes()`' door
        conjunction. `__post_init__` enforces both-or-neither, so either half
        alone filters the same rows -- those mutants are equivalent, not
        defects, and no test should pin a state the type forbids. Dropping
        BOTH halves yields a None key, which `assertNotIn` below catches.
        """
        routes = api_routes()
        self.assertEqual(set(routes), {"table"})
        self.assertNotIn(None, routes)
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

        No caller depends on this yet (see the function's docstring). The
        behaviour is pinned because it is the point of the function: a job row
        records the extractor that ran, and if `api_agent` hid
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

    def test_multimodality_cannot_be_required_without_being_supported(self) -> None:
        """The other half-declared shape. `multimodal_required` is the Table
        Extractor's "no non-multimodal run is meaningful"; `supports_multimodal`
        is the Studio checkbox's existence. Required-but-unsupported describes
        an agent that can neither be run nor configured.
        """
        base = dict(
            key="x", name="X", kind=ExtractorAgentKind.PRIMARY,
            executor="e", ide_operation="o",
        )
        with self.assertRaises(ValueError):
            ExtractorAgentSpec(
                **base, multimodal_required=True, supports_multimodal=False
            )
        # Both set is the Table shape, and is fine.
        self.assertTrue(
            ExtractorAgentSpec(
                **base, multimodal_required=True, supports_multimodal=True
            ).multimodal_required
        )


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

    def test_the_default_is_chosen_by_the_flag_not_by_insertion_order(self) -> None:
        """`simple` is BOTH the first Primary and the flagged one, so deleting
        the `is_default` scan entirely still returns `simple` via the
        defensive fallback. Move the flag to prove the scan is load-bearing.

        What this guards is persisted content: `default_primary_key()` is the
        `agent_key` written onto new and backfilled profile rows, so a
        regression here is silent until profiles are inspected.
        """
        simple = get_agent(ExtractorAgentKey.SIMPLE)
        multi = get_agent(ExtractorAgentKey.MULTI_STAGE)
        with patch.dict(
            EXTRACTOR_AGENTS,
            {
                ExtractorAgentKey.SIMPLE: ExtractorAgentSpec(
                    **{**simple.__dict__, "is_default": False}
                ),
                ExtractorAgentKey.MULTI_STAGE: ExtractorAgentSpec(
                    **{**multi.__dict__, "is_default": True}
                ),
            },
        ):
            self.assertEqual(default_primary_key(), ExtractorAgentKey.MULTI_STAGE)

    def test_the_fallback_applies_when_no_primary_is_flagged(self) -> None:
        """The `catalogue.py` fallback branch, otherwise reached by no test.

        Asserts AVAILABILITY, not insertion order. The sibling test says a new
        profile must never be born pointing at an agent that cannot run, and
        this branch has to honour that too -- `primary_agents()[0]` does not,
        since order is not an availability guarantee.
        """
        patched = {
            key: ExtractorAgentSpec(**{**spec.__dict__, "is_default": False})
            for key, spec in EXTRACTOR_AGENTS.items()
        }
        with patch.dict(EXTRACTOR_AGENTS, patched):
            self.assertTrue(get_agent(default_primary_key()).available)

    def test_the_fallback_skips_an_unavailable_primary(self) -> None:
        """Order alone would return `multi_stage` here."""
        reordered = {
            ExtractorAgentKey.MULTI_STAGE: ExtractorAgentSpec(
                **{
                    **get_agent(ExtractorAgentKey.MULTI_STAGE).__dict__,
                    "is_default": False,
                }
            ),
            ExtractorAgentKey.SIMPLE: ExtractorAgentSpec(
                **{**get_agent(ExtractorAgentKey.SIMPLE).__dict__, "is_default": False}
            ),
        }
        with patch.dict(EXTRACTOR_AGENTS, reordered, clear=True):
            self.assertEqual(default_primary_key(), ExtractorAgentKey.SIMPLE)

    def test_the_default_primary_is_available(self) -> None:
        """A new profile must not be born pointing at an agent that cannot run."""
        self.assertTrue(get_agent(default_primary_key()).available)

    def test_specialized_agents_carry_a_placeholder(self) -> None:
        """Their output is substituted into the schema; without a token it cannot be."""
        for spec in specialized_agents():
            self.assertIsNotNone(spec.schema_placeholder, spec.key)

    def test_the_table_rows_literals_are_pinned(self) -> None:
        """Change-detection on the Table row's three load-bearing strings.

        After cloud #1894 deletes the cloud registry, this row is their only
        definition, so these are single-source pins rather than cross-repo
        ones. `output_key` IS cross-repo and has its own two-sided lock in
        `test_cross_repo_output_key.py`; it is repeated here only so a reader
        of this row sees all three together.
        """
        table = get_agent(ExtractorAgentKey.TABLE)
        self.assertEqual(table.output_key, "tables")
        self.assertEqual(
            table.schema_placeholder, "{{TABLE_EXTRACTOR_AGENT_OUTPUT}}"
        )
        self.assertTrue(table.requires_target_table)

    def test_primary_agents_carry_no_placeholder(self) -> None:
        for spec in primary_agents():
            self.assertIsNone(spec.schema_placeholder, spec.key)

    def test_every_kind_is_one_of_the_two(self) -> None:
        for spec in EXTRACTOR_AGENTS.values():
            self.assertIn(spec.kind, set(ExtractorAgentKind.values), spec.key)

    def test_api_agent_refuses_a_falsy_extractor(self) -> None:
        """`simple` declares `api_extractor=None`, so an unguarded
        `spec.api_extractor == extractor` matches None == None and returns the
        one agent with no API door at all.
        """
        self.assertIsNone(api_agent(None))
        self.assertIsNone(api_agent(""))

    def test_api_extractor_names_are_unique(self) -> None:
        """`api_agent` scans linearly and returns the first match."""
        names = [s.api_extractor for s in EXTRACTOR_AGENTS.values() if s.api_extractor]
        self.assertEqual(len(names), len(set(names)))


class EnumValuesArePersistedLiteralsTest(SimpleTestCase):
    """The enum VALUES are database content; pin them, not just their shape.

    These strings are what ``agentic_extractor_agent_config.agent_key`` and
    ``.kind`` hold, and they are frozen again as literal tuples in the cloud
    app's migration ``0009_extraction_profiles`` -- a repository this CI never
    checks out. A rename is silent at run time: ``get_agent("simple")``
    returns None for every row already written, and ``kind``-filtered queries
    stop matching.

    The sibling tests compare ``EXTRACTOR_AGENTS`` against
    ``ExtractorAgentKey.values``; both sides move together under a rename, so
    only asserting the literals fails.
    """

    # MEMBER -> VALUE, not a set of values: a set is invariant under
    # permutation, so swapping two members' values passes a set-equality pin
    # while every caller of `ExtractorAgentKey.SIMPLE` resolves to the wrong
    # string.
    def test_agent_key_members_map_to_the_persisted_literals(self) -> None:
        self.assertEqual(
            {member.name: member.value for member in ExtractorAgentKey},
            {"SIMPLE": "simple", "MULTI_STAGE": "multi_stage", "TABLE": "table"},
        )

    def test_agent_kind_members_map_to_the_persisted_literals(self) -> None:
        self.assertEqual(
            {member.name: member.value for member in ExtractorAgentKind},
            {"PRIMARY": "primary", "SPECIALIZED": "specialized"},
        )
