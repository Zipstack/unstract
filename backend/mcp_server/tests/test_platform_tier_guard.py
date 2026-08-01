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
