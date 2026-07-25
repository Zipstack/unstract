"""The billable-call budget.

The guard is what stands between an agent in a retry loop and an unbounded LLM
bill, so its edges are pinned here — particularly the one that contradicts the
neighbouring rate-limiter pattern.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from mcp_server import spend_guard
from mcp_server.context import PlatformMCPContext
from mcp_server.platform_views import PlatformMCPServerView
from mcp_server.registry import PLATFORM_TOOLS, MCPTool

ORG = "org-budget"


def a_tool(billable: bool) -> MCPTool:
    return MCPTool(
        name="costly" if billable else "cheap",
        description="d",
        input_schema={"type": "object", "properties": {}},
        handler=lambda ctx: None,
        billable=billable,
        required_method="POST" if billable else "GET",
    )


def context() -> PlatformMCPContext:
    return PlatformMCPContext(
        user=Mock(is_service_account=True),
        platform_key=Mock(permission="read_write"),
        org_name=ORG,
    )


# The guard's behaviour is what is under test, not Redis's. A local-memory
# cache exercises the same django.core.cache API deterministically and without
# requiring live infra, keeping these in the unit tier.
LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mcp-spend-guard-tests",
    }
}


@override_settings(
    MCP_BILLABLE_CALL_LIMIT=3, MCP_BILLABLE_WINDOW_SECONDS=60, CACHES=LOCMEM
)
class SpendGuardTest(SimpleTestCase):
    def setUp(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")

    def tearDown(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")

    def test_budget_allows_up_to_the_limit_then_refuses(self) -> None:
        for expected_used in (1, 2, 3):
            state = spend_guard.consume(ORG)
            assert state.allowed is True
            assert state.used == expected_used

        exhausted = spend_guard.consume(ORG)
        assert exhausted.allowed is False

    def test_exhaustion_message_reads_as_temporary_not_forbidden(self) -> None:
        """An agent that reads this as a permission error stops retrying; one
        that reads it as a wait comes back later. The wording is the only thing
        that distinguishes them.
        """
        for _ in range(4):
            state = spend_guard.consume(ORG)

        message = state.message()
        assert "temporary" in message.lower()
        assert "retry" in message.lower()
        assert "3" in message  # the limit is named

    def test_peek_does_not_consume(self) -> None:
        """whoami calls peek; surfacing the budget must not spend it."""
        spend_guard.consume(ORG)

        before = spend_guard.peek(ORG)
        after = spend_guard.peek(ORG)

        assert before.used == 1
        assert after.used == 1

    def test_budget_is_per_organization(self) -> None:
        for _ in range(4):
            spend_guard.consume(ORG)

        other = spend_guard.consume("org-other-budget")
        try:
            assert other.allowed is True, "one org's spend must not block another's"
        finally:
            cache.delete("mcp:billable:org-other-budget")

    def test_cache_failure_fails_open(self) -> None:
        """This guard bounds runaway loops; it is not a licence check. Taking
        the whole MCP surface offline because Redis blipped would be the worse
        failure, so it allows and logs.
        """
        with patch(
            "mcp_server.spend_guard.cache.add", side_effect=RuntimeError("redis down")
        ):
            state = spend_guard.consume(ORG)

        assert state.allowed is True


@override_settings(
    MCP_BILLABLE_CALL_LIMIT=2, MCP_BILLABLE_WINDOW_SECONDS=60, CACHES=LOCMEM
)
class SpendGuardEnforcementTest(SimpleTestCase):
    def setUp(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")
        self.view = PlatformMCPServerView()

    def tearDown(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")

    def test_only_billable_tools_consume_budget(self) -> None:
        for _ in range(5):
            assert self.view.check_spend_allowed(a_tool(billable=False), context()) is None

        assert spend_guard.peek(ORG).used == 0

    def test_billable_tool_is_refused_once_the_budget_is_spent(self) -> None:
        assert self.view.check_spend_allowed(a_tool(billable=True), context()) is None
        assert self.view.check_spend_allowed(a_tool(billable=True), context()) is None

        refusal = self.view.check_spend_allowed(a_tool(billable=True), context())

        assert refusal is not None
        assert "budget" in refusal.lower()

    def test_budget_is_not_refunded_when_a_tool_then_fails(self) -> None:
        """Deliberately the opposite of the rate-limit slot in tools/execution.

        That slot models concurrency, so releasing it on failure is right. This
        counter models money already spent: a Prompt Studio call that fails
        partway may have burned tokens upstream, and refunding would let an
        agent spend without limit by failing in a loop.
        """
        self.view.check_spend_allowed(a_tool(billable=True), context())
        used_before = spend_guard.peek(ORG).used

        # Simulate the handler blowing up after the budget was claimed.
        try:
            raise RuntimeError("tool exploded")
        except RuntimeError:
            pass

        assert spend_guard.peek(ORG).used == used_before, (
            "budget must not be refunded on failure"
        )

    def test_probing_after_exhaustion_does_not_reset_the_counter(self) -> None:
        for _ in range(2):
            self.view.check_spend_allowed(a_tool(billable=True), context())

        for _ in range(3):
            refusal = self.view.check_spend_allowed(a_tool(billable=True), context())
            assert refusal is not None


@override_settings(
    MCP_BILLABLE_CALL_LIMIT=1, MCP_BILLABLE_WINDOW_SECONDS=60, CACHES=LOCMEM
)
class SpendGuardDispatchTest(SimpleTestCase):
    """The budget as an MCP client actually experiences it.

    The enforcement tests above call the hook directly; this drives the real
    JSON-RPC dispatch, which is where the distinction between "refused
    permanently" and "retry later" is actually made.
    """

    def setUp(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")
        self.view = PlatformMCPServerView()
        self.context = context()

    def tearDown(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")

    def _call_billable(self):
        from dataclasses import replace

        tool = replace(
            PLATFORM_TOOLS.get("executePipeline"),
            handler=lambda ctx, **kw: {"ran": True},
        )
        with patch.object(PLATFORM_TOOLS, "get", return_value=tool):
            response = self.view._call_tool(
                request_id=1,
                params={"name": "executePipeline", "arguments": {}},
                context=self.context,
            )
        return json.loads(response.content)

    def test_first_call_runs_and_second_is_refused_retryably(self) -> None:
        first = self._call_billable()
        assert first["result"]["isError"] is False

        second = self._call_billable()

        # Crucially a *result*, not a JSON-RPC error: clients treat protocol
        # errors as unrecoverable, and this condition clears on its own.
        assert "error" not in second
        assert second["result"]["isError"] is True
        text = second["result"]["content"][0]["text"]
        assert "temporary" in text.lower()
        assert "retry" in text.lower()

    def test_non_billable_tools_still_work_once_the_budget_is_gone(self) -> None:
        """Spending the budget must not take the whole server down with it —
        an agent should still be able to look around and report what happened.
        """
        self._call_billable()
        self._call_billable()  # exhausts

        response = self.view._call_tool(
            request_id=2,
            params={"name": "whoami", "arguments": {}},
            context=self.context,
        )
        body = json.loads(response.content)

        assert body["result"]["isError"] is False


class BillableRegistryInvariantTest(SimpleTestCase):
    def test_every_costly_platform_tool_is_marked_billable(self) -> None:
        """The flag is the only thing wiring a tool into the budget, so a
        costly tool that forgets it is unguarded. Named explicitly rather than
        inferred, so adding one to this list is a deliberate act.
        """
        must_be_billable = {
            "executePipeline",
            "indexDocument",
            "fetchResponse",
            "bulkFetchResponse",
            "singlePassExtraction",
        }

        unguarded = [
            name
            for name in must_be_billable
            if PLATFORM_TOOLS.get(name) is None or not PLATFORM_TOOLS.get(name).billable
        ]

        assert unguarded == [], (
            f"These tools cost money but are not budgeted: {unguarded}"
        )

    def test_billable_tools_are_also_write_gated(self) -> None:
        """Spending money is a write in every sense that matters, so a billable
        tool must never be reachable by a key that cannot write.
        """
        wrong = [
            name
            for name in PLATFORM_TOOLS.names()
            if PLATFORM_TOOLS.get(name).billable
            and PLATFORM_TOOLS.get(name).required_method == "GET"
        ]

        assert wrong == [], f"Billable tools must not be GET-tier: {wrong}"
