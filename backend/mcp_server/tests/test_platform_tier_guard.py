"""The per-tool permission guard on the platform server.

The platform registry is read-only today, so this guard never fires in
practice. It is tested anyway: it exists so that adding the first write tool is
already protected, and an unexercised guard is one that quietly stops working
before anyone depends on it.
"""

from __future__ import annotations

from unittest.mock import Mock

from django.test import SimpleTestCase

from mcp_server.context import PlatformMCPContext
from mcp_server.platform_views import PlatformMCPServerView
from mcp_server.registry import MCPTool, PLATFORM_TOOLS


def a_tool(writes: bool) -> MCPTool:
    return MCPTool(
        name="doThing",
        description="d",
        input_schema={"type": "object", "properties": {}},
        handler=lambda ctx: None,
        writes=writes,
    )


def context_for(tier: str) -> PlatformMCPContext:
    return PlatformMCPContext(
        user=Mock(is_service_account=True),
        platform_key=Mock(permission=tier, name="k"),
        org_name="org-tier",
    )


class PlatformTierGuardTest(SimpleTestCase):
    def setUp(self) -> None:
        self.view = PlatformMCPServerView()

    def test_read_tier_is_refused_a_write_tool(self) -> None:
        refusal = self.view.check_tool_allowed(a_tool(writes=True), context_for("read"))

        assert refusal is not None
        assert "read_write" in refusal

    def test_read_write_tier_is_allowed_a_write_tool(self) -> None:
        assert (
            self.view.check_tool_allowed(a_tool(writes=True), context_for("read_write"))
            is None
        )

    def test_read_tier_is_allowed_a_read_tool(self) -> None:
        """The guard must not block reads — a read key that reaches the server
        should still be able to use every read tool on it.
        """
        assert (
            self.view.check_tool_allowed(a_tool(writes=False), context_for("read"))
            is None
        )

    def test_platform_registry_is_entirely_read_only(self) -> None:
        """Pins the documented promise that this server changes nothing.

        If someone registers a write tool here, this fails and forces them to
        confirm the tier guard and the README claim still hold.
        """
        writers = [
            name for name in PLATFORM_TOOLS.names() if PLATFORM_TOOLS.get(name).writes
        ]

        assert writers == [], (
            f"Platform MCP server advertises itself as read-only but exposes "
            f"write tools: {writers}"
        )
