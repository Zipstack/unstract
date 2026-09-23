"""Per-tool authorization on the platform server.

The auth middleware checks the key's permission tier against the request's HTTP
method — but every JSON-RPC message arrives as an HTTP POST whatever the tool
inside it does, so the middleware's verdict cannot distinguish
``listWorkflows`` from ``executePipeline``. This guard re-applies the tier
against the method each tool *declares*, and is the only thing standing between
a low-tier key and a write tool.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from platform_api.models import ApiKeyPermission

from mcp_server.context import PlatformMCPContext
from mcp_server.platform_views import PlatformMCPServerView
from mcp_server.registry import PLATFORM_TOOLS, MCPTool


def a_tool(required_method: str, writes: bool = True) -> MCPTool:
    return MCPTool(
        name="doThing",
        description="d",
        input_schema={"type": "object", "properties": {}},
        handler=lambda ctx: None,
        writes=writes,
        required_method=required_method,
    )


def context_for(tier: str) -> PlatformMCPContext:
    return PlatformMCPContext(
        user=Mock(is_service_account=True),
        platform_key=Mock(permission=tier),
        org_name="org-tier",
    )


class PlatformTierGuardTest(SimpleTestCase):
    def setUp(self) -> None:
        self.view = PlatformMCPServerView()

    def test_tier_matrix(self) -> None:
        """The whole authorization model in one table.

        Mirrors ``ApiKeyPermission.allows`` deliberately: if that mapping ever
        changes, this fails and forces the MCP surface to be reconsidered
        rather than silently inheriting a wider grant.
        """
        cases = [
            # tier,         method,     allowed
            ("read", "GET", True),
            ("read", "POST", False),
            ("read", "DELETE", False),
            ("read_write", "GET", True),
            ("read_write", "POST", True),
            # read_write must NOT reach destructive tools.
            ("read_write", "DELETE", False),
            ("full_access", "GET", True),
            ("full_access", "POST", True),
            ("full_access", "DELETE", True),
        ]
        for tier, method, allowed in cases:
            with self.subTest(f"{tier} -> {method}"):
                refusal = self.view.check_tool_allowed(a_tool(method), context_for(tier))
                assert (refusal is None) == allowed, (
                    f"{tier} {method}: expected allowed={allowed}, got {refusal!r}"
                )

    def test_refusal_names_the_tool_and_the_tier(self) -> None:
        """The refusal is read by an agent, which should be able to tell its
        operator what to change rather than just retrying.
        """
        refusal = self.view.check_tool_allowed(
            a_tool("DELETE"), context_for("read_write")
        )

        assert "doThing" in refusal
        assert "DELETE" in refusal
        assert "read_write" in refusal

    def test_unrecognised_tier_is_refused(self) -> None:
        refusal = self.view.check_tool_allowed(a_tool("GET"), context_for("wat"))

        assert refusal is not None

    def test_every_write_tool_declares_a_non_get_method(self) -> None:
        """The invariant that keeps the guard meaningful.

        A ``writes=True`` tool left at the default ``required_method="GET"``
        would be reachable by any key that can reach the server at all — the
        guard would pass it silently. This is what makes registering a write
        tool safe by default.
        """
        unguarded = [
            name
            for name in PLATFORM_TOOLS.names()
            if PLATFORM_TOOLS.get(name).writes
            and PLATFORM_TOOLS.get(name).required_method == "GET"
        ]

        assert unguarded == [], (
            f"These platform tools mutate state but declare required_method="
            f"'GET', so the tier guard will not protect them: {unguarded}"
        )

    def test_registering_an_unguarded_write_tool_is_refused(self) -> None:
        """The invariant above is now enforced at registration, not only here.

        A CI assertion can be deselected, or simply not run on the branch that
        adds the tool; a registration-time refusal means a wrongly declared
        tool cannot reach a running server at all.
        """
        from mcp_server.registry import MCPToolRegistry

        registry = MCPToolRegistry()

        with self.assertRaises(ValueError) as caught:
            registry.register(
                MCPTool(
                    name="deleteEverything",
                    description="",
                    input_schema={},
                    handler=lambda context: None,
                    writes=True,
                )
            )

        assert "required_method='GET'" in str(caught.exception)

    def test_a_truthfully_declared_write_tool_registers(self) -> None:
        """The invariant is satisfiable, not merely restrictive.

        It applies to both registries. The deployment server has no tiers — it
        does not override ``check_tool_allowed``, so ``required_method`` is
        unread there — but declaring it truthfully costs nothing and keeps the
        check unconditional rather than opt-in.
        """
        from mcp_server.registry import MCPToolRegistry

        registry = MCPToolRegistry()

        registry.register(
            MCPTool(
                name="extractSomething",
                description="",
                input_schema={},
                handler=lambda context: None,
                writes=True,
                required_method="POST",
            )
        )

        assert registry.get("extractSomething") is not None

    def test_no_credential_tools_are_exposed(self) -> None:
        """API key creation and rotation return the secret in their response.

        Exposing either as an MCP tool would hand an agent — one that may be
        processing untrusted document content — a way to mint or exfiltrate
        credentials. Named explicitly so adding one is a deliberate act.
        """
        forbidden = ("key", "credential", "secret", "token", "rotate")
        offenders = [
            name
            for name in PLATFORM_TOOLS.names()
            if any(word in name.lower() for word in forbidden)
        ]

        assert offenders == [], (
            f"Platform MCP server must not expose credential tools: {offenders}"
        )


class TierGuardIsProspectiveTest(SimpleTestCase):
    """The per-tool tier guard refuses nothing today — deliberately.

    Raised in review as a design question worth answering explicitly rather
    than leaving implicit: is the tier model doing what we think it does?

    It is not, *yet*. A `read` key cannot reach the view (the middleware
    rejects POST on tier before dispatch), and both remaining tiers allow POST
    while every tool declares GET or POST. So `check_tool_allowed` never
    refuses a request that reaches it. That is defense-in-depth for the day a
    DELETE-tier tool is added, or the day the middleware grows an MCP carve-out.

    Pinned here so the fact is a tripwire rather than something a future
    reader re-derives: when this test starts failing, the guard has begun doing
    real work and the docstrings claiming otherwise need updating.
    """

    def test_no_tool_declares_delete_today(self) -> None:
        methods = {
            PLATFORM_TOOLS.get(name).required_method for name in PLATFORM_TOOLS.names()
        }

        assert methods <= {"GET", "POST"}, (
            f"A tool now declares {sorted(methods - {'GET', 'POST'})}. The tier "
            "guard has started refusing real calls — update the docstrings in "
            "platform_views.check_tool_allowed that say it refuses nothing."
        )

    def test_the_guard_refuses_nothing_for_tiers_that_can_reach_it(self) -> None:
        """Both halves of the reviewer's trace, asserted rather than argued."""
        for permission in ApiKeyPermission:
            if not permission.allows("POST"):
                # Cannot reach the view at all; the middleware stops it first.
                continue
            refused = [
                name
                for name in PLATFORM_TOOLS.names()
                if not permission.allows(PLATFORM_TOOLS.get(name).required_method)
            ]
            with self.subTest(permission.value):
                assert refused == [], (
                    f"Tier '{permission.value}' now refuses {refused}. The guard "
                    "is doing real work — see the note above."
                )

    def test_a_read_key_cannot_reach_the_server_at_all(self) -> None:
        """The documented minimum tier, pinned to the permission model.

        `whoami` and the README both state `read_write` is required *including*
        for read tools. That claim is only true while `read` disallows POST.
        """
        assert ApiKeyPermission("read").allows("POST") is False
        assert ApiKeyPermission("read_write").allows("POST") is True

    def test_whoami_states_the_minimum_tier(self) -> None:
        """An agent holding a read key never reaches whoami, but one holding a
        read_write key needs to know why its tier is the floor — otherwise
        `can_use_write_tools: false` reads as "read tools still work", which
        would be wrong for a read key.
        """
        from unittest.mock import Mock, patch

        from mcp_server.tools.platform import whoami

        context = Mock()
        context.org_name = "org-mcp"
        context.platform_key = Mock(name="k", permission="read_write")
        context.user = Mock(is_service_account=True)

        with patch("mcp_server.spend_guard.peek") as peek:
            peek.return_value = Mock(used=0, limit=50, window_seconds=3600)
            result = whoami(context)

        assert result["minimum_tier"] == "read_write"
        assert "read_write" in result["tier_note"]
