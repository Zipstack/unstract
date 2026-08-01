"""The billable-call budget.

The guard is what stands between an agent in a retry loop and an unbounded LLM
bill, so its edges are pinned here — particularly the one that contradicts the
neighbouring rate-limiter pattern.
"""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import redis
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from mcp_server import spend_guard
from mcp_server.context import PlatformMCPContext
from mcp_server.exceptions import MCPToolError
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
        broken = Mock()
        broken.add.side_effect = redis.ConnectionError("redis down")
        with patch("mcp_server.spend_guard.get_cache", return_value=broken):
            state = spend_guard.consume(ORG)

        assert state.allowed is True

    def test_a_bug_in_the_cache_path_is_not_swallowed(self) -> None:
        """Fail-open covers the cache being unreachable, not every error.

        A bare ``except Exception`` here would also absorb a TypeError or any
        future defect in this module and return allowed=True — silently
        unbudgeting every billable call in the deployment, with a log line as
        the only signal. A real bug must surface.
        """
        broken = Mock()
        broken.add.side_effect = TypeError("bad key type")
        with patch("mcp_server.spend_guard.get_cache", return_value=broken):
            with self.assertRaises(TypeError):
                spend_guard.consume(ORG)

    def test_reseed_failure_also_fails_open(self) -> None:
        """The add/incr expiry race must not invert the documented behaviour.

        ``incr`` raising ValueError means the key expired between the two
        calls; if Redis then drops during the re-seed, an unguarded
        ``cache.set`` would raise out of ``consume`` and fail *closed* — a 500
        on a billable call, the opposite of everything above.
        """
        broken = Mock()
        broken.incr.side_effect = ValueError("key expired")
        broken.set.side_effect = redis.ConnectionError("redis down")
        with patch("mcp_server.spend_guard.get_cache", return_value=broken):
            state = spend_guard.consume(ORG)

        assert state.allowed is True

    def test_peek_also_fails_open(self) -> None:
        """whoami reports the budget, so an unreachable cache must not break it."""
        broken = Mock()
        broken.get.side_effect = redis.ConnectionError("redis down")
        with patch("mcp_server.spend_guard.get_cache", return_value=broken):
            state = spend_guard.peek(ORG)

        assert state.allowed is True
        assert state.used == 0


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
            # The real preflight resolves a pipeline_id against the DB, which
            # this unit-tier test has no fixture for. Budget behaviour is what
            # is under test here; preflight has its own tests below.
            preflight=None,
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


class CacheSelectionTest(SimpleTestCase):
    """The budget lives in the project's shared Django cache.

    There is no MCP-specific DB knob: it was unreachable at its shipped default
    and built a fresh connection pool per billable call when set. Using the
    shared cache is also what keeps ``override_settings(CACHES=...)`` working
    in the tests above.
    """

    def test_budget_uses_the_shared_django_cache(self) -> None:
        from django.core.cache import cache as django_cache

        assert spend_guard.get_cache() is django_cache


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
            # The most expensive tool on the server: it runs a whole
            # extraction workflow and consumes the org's extraction quota.
            "extractDocument",
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


@override_settings(
    MCP_BILLABLE_CALL_LIMIT=2, MCP_BILLABLE_WINDOW_SECONDS=60, CACHES=LOCMEM
)
class PreflightProtectsTheBudgetTest(SimpleTestCase):
    """A call that could never have run must not cost a billable slot.

    The budget is consumed on invocation and never refunded, which is right
    for a call that may have spent tokens upstream — but wrong for one refused
    on an argument the server could check for free. ``extractDocument`` is the
    case that motivated this: ``api_name`` is caller-supplied prose rather than
    an id copied from a listing, so an agent guessing at names could exhaust
    the window without ever reaching an LLM.
    """

    def setUp(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")
        self.view = PlatformMCPServerView()
        self.context = context()

    def tearDown(self) -> None:
        cache.delete(f"mcp:billable:{ORG}")

    def _call(self, tool: MCPTool, arguments: dict):
        with patch.object(PLATFORM_TOOLS, "get", return_value=tool):
            response = self.view._call_tool(
                request_id=1,
                params={"name": tool.name, "arguments": arguments},
                context=self.context,
            )
        return json.loads(response.content)

    def _billable_tool(self, preflight) -> MCPTool:
        from dataclasses import replace

        return replace(
            PLATFORM_TOOLS.get("extractDocument"),
            handler=lambda ctx, **kw: {"ran": True},
            preflight=preflight,
        )

    def test_a_failed_preflight_does_not_consume_budget(self) -> None:
        def refuse(ctx, **kwargs):
            raise MCPToolError("No API deployment named 'typo'.")

        body = self._call(self._billable_tool(refuse), {"api_name": "typo"})

        assert body["result"]["isError"] is True
        assert "typo" in body["result"]["content"][0]["text"]
        assert spend_guard.peek(ORG).used == 0, (
            "a call refused before it could run must not cost a billable slot"
        )

    def test_repeated_bad_names_never_exhaust_the_window(self) -> None:
        """The failure mode this exists to prevent: an agent guessing at
        deployment names locking the organization out of real extractions.
        """

        def refuse(ctx, **kwargs):
            raise MCPToolError("No such deployment.")

        for _ in range(5):
            self._call(self._billable_tool(refuse), {"api_name": "guess"})

        assert spend_guard.peek(ORG).used == 0

        # The budget is still intact for a call that does resolve.
        body = self._call(self._billable_tool(lambda ctx, **kw: None), {})
        assert body["result"]["isError"] is False
        assert spend_guard.peek(ORG).used == 1

    def test_a_passing_preflight_still_consumes_budget(self) -> None:
        """Preflight guards the budget; it must not become a way around it."""
        body = self._call(self._billable_tool(lambda ctx, **kw: None), {})

        assert body["result"]["isError"] is False
        assert spend_guard.peek(ORG).used == 1

    def test_preflight_runs_before_the_budget_not_merely_instead_of_it(self) -> None:
        """Ordering, pinned directly.

        If the budget were claimed first and the preflight merely reported the
        refusal, the counter would still have moved. Exhausting the budget and
        then calling with a bad name distinguishes the two: with correct
        ordering the caller is told the name is wrong, not that it is broke.
        """

        def refuse(ctx, **kwargs):
            raise MCPToolError("No API deployment named 'typo'.")

        for _ in range(2):
            self._call(self._billable_tool(lambda ctx, **kw: None), {})
        assert spend_guard.peek(ORG).used == 2  # exhausted

        body = self._call(self._billable_tool(refuse), {"api_name": "typo"})

        text = body["result"]["content"][0]["text"]
        assert "typo" in text, f"budget refusal masked the real problem: {text}"

    def test_every_billable_tool_has_a_preflight(self) -> None:
        """Each billable tool resolves something before it spends, so each can
        refuse for free. A new one without a preflight silently reintroduces
        the burn-a-slot-on-a-typo behaviour.
        """
        unguarded = [
            name
            for name in PLATFORM_TOOLS.names()
            if PLATFORM_TOOLS.get(name).billable
            and PLATFORM_TOOLS.get(name).preflight is None
        ]

        assert unguarded == [], (
            "These billable tools consume budget before validating their "
            f"arguments: {unguarded}. Give each a preflight that resolves its "
            "target, or state here why it cannot fail cheaply."
        )
