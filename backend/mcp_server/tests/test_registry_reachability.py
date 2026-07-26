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
    "execution_id": "listExecutions",
}

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
            if argument in required and argument.endswith(("_id", "_ids")):
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
