"""Every id a tool asks for must be obtainable from another tool.

An MCP client sees only ``tools/list``. It has no database, no UI and no way to
guess a UUID, so a tool whose required argument no other tool ever returns is
dead on arrival — it will be listed, attempted, and fail every time.

This shipped once already: the four billable Prompt Studio tools all required a
``document_id`` while nothing in the registry produced one, which made the most
expensive tools on the server the only unreachable ones. The failure was
invisible because each tool was correct in isolation; only the registry as a
whole was wrong. So the invariant is asserted over the registry, not per tool.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from mcp_server.registry import DEPLOYMENT_TOOLS, PLATFORM_TOOLS

# Which tool an agent is expected to call to obtain each opaque id.
#
# Written out rather than inferred from response shapes: handlers return plain
# dicts built at runtime, so inference would mean executing them, and a map
# that guesses would quietly bless the next unreachable id. Adding an entry
# here is a deliberate statement that the named tool really does return it.
PLATFORM_ID_PRODUCERS = {
    "project_id": "listPromptStudioProjects",
    "document_id": "listPromptStudioDocuments",
    "prompt_id": "listPrompts",
    "prompt_ids": "listPrompts",
    "pipeline_id": "listPipelines",
    "workflow_id": "listWorkflows",
    "api_id": "listApiDeployments",
    # listExecutions produces ids for past runs; extractDocument returns the id
    # of the run it just started. Either is a valid handle for polling.
    "execution_id": "listExecutions",
    # Not an id by name, but just as unguessable: an agent cannot invent a
    # deployment's api_name any more than it can invent a UUID.
    "api_name": "listApiDeployments",
}

# Argument names that identify a specific resource the caller must already
# know. Extends past the ``_id`` suffix because ``api_name`` is an opaque
# handle in every way that matters here.
_OPAQUE_SUFFIXES = ("_id", "_ids", "_name")

DEPLOYMENT_ID_PRODUCERS = {
    # The deployment server is scoped to a single API, and its execution id is
    # handed back by the extraction call itself rather than by a listing.
    "execution_id": "extractDocument",
}


def _required_ids(registry) -> dict[str, list[str]]:
    """Map each id-shaped argument to the tools that require it."""
    consumed: dict[str, list[str]] = {}
    for name in registry.names():
        schema = registry.get(name).input_schema
        required = set(schema.get("required", []))
        for argument in schema.get("properties", {}):
            if argument in required and argument.endswith(_OPAQUE_SUFFIXES):
                consumed.setdefault(argument, []).append(name)
    return consumed


class PlatformRegistryReachabilityTest(SimpleTestCase):
    def test_every_required_id_has_a_declared_producer(self) -> None:
        consumed = _required_ids(PLATFORM_TOOLS)

        unproducible = {
            argument: tools
            for argument, tools in consumed.items()
            if argument not in PLATFORM_ID_PRODUCERS
        }

        assert unproducible == {}, (
            "These tools require an id no tool is declared to produce, so an "
            f"agent can never call them: {unproducible}. Either add the tool "
            "that returns the id, or record its producer in "
            "PLATFORM_ID_PRODUCERS."
        )

    def test_every_declared_producer_is_actually_registered(self) -> None:
        """The map is only as good as its referents.

        A producer that was renamed or dropped would leave the test above
        passing while the id became unobtainable again.
        """
        missing = sorted(
            {
                producer
                for producer in PLATFORM_ID_PRODUCERS.values()
                if PLATFORM_TOOLS.get(producer) is None
            }
        )

        assert missing == [], f"Declared id producers are not registered: {missing}"

    def test_the_billable_prompt_studio_chain_is_walkable(self) -> None:
        """The specific path that was broken, pinned end to end.

        Named separately from the general invariant because this is the
        sequence an agent must actually perform to spend money: project, then
        document, then prompt, then the billable call.
        """
        for step in (
            "listPromptStudioProjects",
            "listPromptStudioDocuments",
            "listPrompts",
            "fetchResponse",
        ):
            assert PLATFORM_TOOLS.get(step) is not None, f"{step} is missing"

        for producer in ("listPromptStudioDocuments", "listPrompts"):
            tool = PLATFORM_TOOLS.get(producer)
            assert tool.billable is False, (
                f"{producer} exists so an agent can find ids before spending; "
                "making it billable would put the discovery step behind the "
                "budget it is meant to help the agent respect."
            )
            assert tool.required_method == "GET", (
                f"{producer} only reads, so a read-tier key must reach it — "
                "otherwise the billable tools stay unreachable for that key."
            )


class DeploymentRegistryReachabilityTest(SimpleTestCase):
    def test_every_required_id_has_a_declared_producer(self) -> None:
        consumed = _required_ids(DEPLOYMENT_TOOLS)

        unproducible = {
            argument: tools
            for argument, tools in consumed.items()
            if argument not in DEPLOYMENT_ID_PRODUCERS
        }

        assert unproducible == {}, (
            f"Unreachable on the deployment server: {unproducible}"
        )


class ReadMeFirstMatchesTheRegistryTest(SimpleTestCase):
    """``readMeFirst`` must name every tool the server actually exposes.

    This is the tool whose entire job is telling an agent how to reach the
    others, and its listing is hand-maintained prose rather than a projection
    of the registry — so it drifts silently. It already did: the two tools that
    produce ``document_id`` and ``prompt_id`` were added to the registry and
    not to the guide, leaving an agent that trusts the guide able to see the
    billable tools with no way to call them.

    Kept as a listing rather than generated from the registry on purpose. The
    ``purpose`` text is written for an agent deciding *whether* to call a tool
    — which is worth more than the tool's own description — so the value is in
    a human writing it. This test only enforces that the set is complete.
    """

    # Keys in the platform guide that enumerate tools. Named explicitly so
    # adding a new grouping is a deliberate act rather than a silent hole.
    PLATFORM_LISTING_KEYS = (
        "discovery_tools",
        "observability_tools",
        "state_change_tools",
        "billable_tools",
    )

    def _named_in(self, guide: dict, keys) -> set[str]:
        return {
            entry["name"]
            for key in keys
            for entry in guide[key]
            if isinstance(entry, dict) and "name" in entry
        }

    def test_platform_guide_names_every_platform_tool(self) -> None:
        from mcp_server.tools.platform import platform_read_me_first

        guide = platform_read_me_first(
            Mock(org_name="org-guide", platform_key=Mock(permission="read_write"))
        )
        listed = self._named_in(guide, self.PLATFORM_LISTING_KEYS)

        # readMeFirst does not list itself; an agent has already called it.
        registered = set(PLATFORM_TOOLS.names()) - {"readMeFirst"}

        assert registered - listed == set(), (
            f"readMeFirst does not mention {sorted(registered - listed)}. An "
            "agent that trusts the guide will never call them — add each to "
            "the appropriate listing in platform_read_me_first."
        )
        assert listed - registered == set(), (
            f"readMeFirst advertises tools that do not exist: "
            f"{sorted(listed - registered)}."
        )

    def test_billable_tools_are_listed_as_billable(self) -> None:
        """A costly tool listed under discovery reads as free to call.

        The grouping is the guide's main signal about consequence, so a tool
        in the wrong group actively misleads rather than merely omitting.
        """
        from mcp_server.tools.platform import platform_read_me_first

        guide = platform_read_me_first(
            Mock(org_name="org-guide", platform_key=Mock(permission="read_write"))
        )
        listed_billable = self._named_in(guide, ("billable_tools",))
        actually_billable = {
            name for name in PLATFORM_TOOLS.names() if PLATFORM_TOOLS.get(name).billable
        }

        assert listed_billable == actually_billable, (
            "readMeFirst's billable_tools must match the registry's billable "
            f"flags exactly. Listed: {sorted(listed_billable)}, actual: "
            f"{sorted(actually_billable)}."
        )

    def test_free_tools_are_not_listed_as_billable(self) -> None:
        """The producers exist so an agent can find ids *before* spending.

        Listing them as billable would push an agent to avoid the very step
        that makes the billable tools callable.
        """
        from mcp_server.tools.platform import platform_read_me_first

        guide = platform_read_me_first(
            Mock(org_name="org-guide", platform_key=Mock(permission="read_write"))
        )
        listed_discovery = self._named_in(guide, ("discovery_tools",))

        for producer in ("listPromptStudioDocuments", "listPrompts"):
            assert producer in listed_discovery, (
                f"{producer} produces the ids the billable tools need, so it "
                "belongs in discovery_tools where an agent looks first."
            )

    def test_deployment_guide_names_every_deployment_tool(self) -> None:
        from mcp_server.tools.info import read_me_first

        guide = read_me_first(
            Mock(api=Mock(display_name="d", description="x", is_active=True))
        )
        listed = self._named_in(guide, ("tools",))
        registered = set(DEPLOYMENT_TOOLS.names()) - {"readMeFirst"}

        assert listed == registered, (
            f"Deployment readMeFirst is out of sync. Missing: "
            f"{sorted(registered - listed)}, phantom: {sorted(listed - registered)}."
        )


class PlatformExtractionShapeTest(SimpleTestCase):
    """Invariants of extraction on the organization-scoped server.

    Both servers run the same extraction. What differs is the credential, and
    two consequences of that are enforced here because neither is visible at
    the call site.
    """

    def test_platform_extraction_does_not_offer_an_llm_profile(self) -> None:
        """The coupling that keeps a missing api_key from ever being read.

        ``ExecutionRequestSerializer.validate_llm_profile_id`` resolves the
        profile against the API key's owner. A platform caller has no
        deployment key — ``MCPContext.api_key`` is None — and the only reason
        that is safe is that this argument is never offered, so DRF never runs
        that validator. Adding the field back would surface as "Unable to
        validate LLM profile ownership" from a code path with no obvious link
        to this schema.
        """
        schema = PLATFORM_TOOLS.get("extractDocument").input_schema

        assert "llm_profile_id" not in schema["properties"], (
            "llm_profile_id is validated against the API key's owner, which a "
            "platform key does not have. Offering it here would either break "
            "at runtime or require borrowing another principal's key."
        )

    def test_platform_extraction_still_mirrors_the_deployment_limits(self) -> None:
        """The platform schema is derived from the deployment one, so the file
        cap and tag rules cannot drift between the two servers.
        """
        platform = PLATFORM_TOOLS.get("extractDocument").input_schema["properties"]
        deployment = DEPLOYMENT_TOOLS.get("extractDocument").input_schema["properties"]

        assert platform["document_urls"] == deployment["document_urls"]
        assert platform["timeout"] == deployment["timeout"]
        assert platform["tags"] == deployment["tags"]

    def test_platform_extraction_requires_naming_a_deployment(self) -> None:
        """The deployment server gets its target from the credential; here the
        agent must name one, so it is required rather than optional.
        """
        schema = PLATFORM_TOOLS.get("extractDocument").input_schema

        assert "api_name" in schema["required"]
        assert "document_urls" in schema["required"]

    def test_polling_is_free_but_extracting_is_not(self) -> None:
        """An agent told that polling costs money will avoid polling, which is
        the one thing it should do freely while waiting.
        """
        assert PLATFORM_TOOLS.get("extractDocument").billable is True
        assert PLATFORM_TOOLS.get("getExecutionStatus").billable is False
        assert PLATFORM_TOOLS.get("getExecutionStatus").required_method == "GET"


class ToolAnnotationsTest(SimpleTestCase):
    """`tools/list` advertises behaviour hints a host can act on.

    Without these every tool looks equally dangerous, so a host cannot
    auto-approve `listWorkflows` while prompting on `executePipeline` — which
    is what makes a 23-tool surface tolerable.

    Spec defaults are the trap (`ToolAnnotations`, rev 2025-06-18):
    `readOnlyHint` defaults to false and `destructiveHint` defaults to *true*,
    so silence is the unsafe answer in both directions and every value here is
    stated explicitly.
    """

    def test_every_tool_advertises_annotations_and_a_title(self) -> None:
        for registry in (DEPLOYMENT_TOOLS, PLATFORM_TOOLS):
            for schema in registry.list_schemas():
                with self.subTest(schema["name"]):
                    assert schema["title"], "a host shows this in its UI"
                    hints = schema["annotations"]
                    assert hints["title"] == schema["title"]
                    assert isinstance(hints["readOnlyHint"], bool)
                    assert hints["openWorldHint"] is True

    def test_read_tools_are_marked_read_only(self) -> None:
        """The whole point: a host can auto-approve these."""
        for registry in (DEPLOYMENT_TOOLS, PLATFORM_TOOLS):
            for name in registry.names():
                tool = registry.get(name)
                if tool.writes or tool.billable:
                    continue
                with self.subTest(name):
                    assert tool.annotations()["readOnlyHint"] is True

    def test_writing_tools_are_never_marked_read_only(self) -> None:
        """The inverse, and the one that matters for safety: a tool that
        spends money or changes state must not be advertised as inert.
        """
        for registry in (DEPLOYMENT_TOOLS, PLATFORM_TOOLS):
            for name in registry.names():
                tool = registry.get(name)
                if not (tool.writes or tool.billable):
                    continue
                with self.subTest(name):
                    assert tool.annotations()["readOnlyHint"] is False

    def test_read_tools_omit_the_write_only_hints(self) -> None:
        """`destructiveHint`/`idempotentHint` are defined as meaningful only
        when `readOnlyHint` is false, so emitting them for a read tool would
        publish a value the client is told to ignore.
        """
        tool = PLATFORM_TOOLS.get("listWorkflows")
        hints = tool.annotations()

        assert "destructiveHint" not in hints
        assert "idempotentHint" not in hints

    def test_no_tool_is_advertised_as_destructive(self) -> None:
        """Every write tool here is reversible and none deletes anything —
        a deliberate property of this surface, stated rather than left to the
        spec default of true.
        """
        for registry in (DEPLOYMENT_TOOLS, PLATFORM_TOOLS):
            for name in registry.names():
                tool = registry.get(name)
                with self.subTest(name):
                    assert tool.annotations().get("destructiveHint") is not True

    def test_state_changes_are_idempotent_and_executions_are_not(self) -> None:
        """The distinction a host needs to decide whether a retry is safe."""
        for name in ("setApiDeploymentActive", "setPipelineActive"):
            with self.subTest(name):
                assert PLATFORM_TOOLS.get(name).annotations()["idempotentHint"] is True

        for name in ("executePipeline", "indexDocument", "singlePassExtraction"):
            with self.subTest(name):
                assert PLATFORM_TOOLS.get(name).annotations()["idempotentHint"] is False

    def test_deployment_extract_is_not_advertised_as_repeatable(self) -> None:
        """The case that broke a derived-from-`billable` implementation.

        Deployment `extractDocument` is not billable — the deployment server
        has no spend guard, its cost is bounded by the rate limiter — but it
        still starts a fresh execution per call, so it must not be advertised
        as safe to repeat.
        """
        tool = DEPLOYMENT_TOOLS.get("extractDocument")

        assert tool.billable is False
        assert tool.annotations()["idempotentHint"] is False


class ToolCountIsDocumentedTest(SimpleTestCase):
    """The advertised tool count matches the registry.

    Review found the PR description claiming 19 platform tools against 23
    registered — the listing had not kept up as tools were added. That is the
    kind of drift nobody notices, because the docs are read by people and the
    registry is read by machines.

    This pins the number so adding a tool forces a deliberate decision about
    where it is announced. If it fails, update the count *and* the tool tables
    in README.md and the PR description, not just this constant.
    """

    EXPECTED_PLATFORM_TOOLS = 23
    EXPECTED_DEPLOYMENT_TOOLS = 4

    def test_platform_tool_count(self) -> None:
        actual = len(PLATFORM_TOOLS.names())

        assert actual == self.EXPECTED_PLATFORM_TOOLS, (
            f"Platform registry has {actual} tools, docs say "
            f"{self.EXPECTED_PLATFORM_TOOLS}. Update README.md's tool tables "
            "and the PR/release notes, then this constant."
        )

    def test_deployment_tool_count(self) -> None:
        actual = len(DEPLOYMENT_TOOLS.names())

        assert actual == self.EXPECTED_DEPLOYMENT_TOOLS, (
            f"Deployment registry has {actual} tools, docs say "
            f"{self.EXPECTED_DEPLOYMENT_TOOLS}. Update README.md's tool table, "
            "then this constant."
        )

    def test_the_readme_lists_every_platform_tool(self) -> None:
        """Counting alone would pass if one tool were swapped for another."""
        from pathlib import Path

        readme = (
            Path(__file__).resolve().parent.parent / "README.md"
        ).read_text()

        missing = [
            name for name in PLATFORM_TOOLS.names() if f"`{name}`" not in readme
        ]

        assert missing == [], (
            f"These platform tools are registered but absent from README.md: "
            f"{missing}. An agent's operator reads that table to know what the "
            "credential can reach."
        )
