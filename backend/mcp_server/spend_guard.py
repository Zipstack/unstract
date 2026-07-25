"""Per-organization budget for billable MCP tool calls.

Some platform tools cost real money each time they run: they drive LLM
inference, embedding and vector-store writes. An agent looping over a list, or
retrying on a misread error, can spend a great deal without anyone watching. So
billable tools are budgeted per organization over a rolling window.

**This is a call budget, not a spend budget.** It counts invocations, not
tokens or currency. Unstract's open-source backend records usage after the fact
(``usage_v2`` aggregates what was consumed) but has no pre-flight token
allowance to check against — subscription and quota enforcement live in the
enterprise overlay, which this app cannot depend on. A call counter is the
strongest guard implementable here, and it is a blunt one: it bounds *how many
times* an agent can trigger billable work, not how expensive each call is.

Two properties are deliberate and easy to get backwards:

* **Consumption happens on invocation and is never refunded**, including when
  the tool then fails. A failed Prompt Studio call may already have spent
  tokens upstream, and refunding on failure would let an agent burn unbounded
  spend by triggering failures in a loop. This is the opposite of the
  rate-limit slot handling in ``tools/execution.py``, where the slot models
  concurrency rather than cost — see ``test_spend_guard`` for the pin.
* **Exhaustion is temporary, not a permission error.** The caller is told when
  the window resets so it can retry later, rather than concluding the tool is
  forbidden and giving up.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Key namespace. The window start is not encoded in the key: the TTL is what
# expires the counter, giving a fixed window that begins at the first billable
# call rather than at a wall-clock boundary.
_KEY_PREFIX = "mcp:billable"


def _key(org_id: str) -> str:
    return f"{_KEY_PREFIX}:{org_id}"


@dataclass(frozen=True)
class BudgetState:
    """The outcome of a budget check."""

    allowed: bool
    used: int
    limit: int
    window_seconds: int
    retry_after_seconds: int | None = None

    def message(self) -> str:
        """Explain exhaustion to the calling agent.

        Written so the agent understands this is a wait, not a refusal — and
        knows roughly how long to wait.
        """
        minutes = max(1, round((self.retry_after_seconds or self.window_seconds) / 60))
        return (
            f"This organization has used its budget for billable MCP "
            f"operations ({self.used}/{self.limit} in the last "
            f"{round(self.window_seconds / 60)} minutes). This is a temporary "
            f"limit, not a permission problem — retry in about {minutes} "
            f"minute(s), or ask an administrator to raise "
            f"MCP_BILLABLE_CALL_LIMIT."
        )


def get_limit() -> int:
    return int(getattr(settings, "MCP_BILLABLE_CALL_LIMIT", 50))


def get_window_seconds() -> int:
    return int(getattr(settings, "MCP_BILLABLE_WINDOW_SECONDS", 3600))


def peek(org_id: str) -> BudgetState:
    """Report budget state without consuming any of it.

    Used by ``whoami`` so an agent can pace itself instead of discovering the
    limit by hitting it.
    """
    limit = get_limit()
    window = get_window_seconds()
    try:
        used = cache.get(_key(org_id)) or 0
    except Exception as error:
        # Reporting the budget must never be the thing that breaks whoami —
        # `consume` fails open for the same reason, and a read is even less
        # load-bearing than a claim.
        logger.warning(f"MCP spend guard unreadable for org '{org_id}': {error}")
        used = 0
    return BudgetState(
        allowed=used < limit, used=used, limit=limit, window_seconds=window
    )


def consume(org_id: str) -> BudgetState:
    """Claim one billable call for this organization.

    Returns a state with ``allowed=False`` when the budget is already spent, in
    which case nothing is consumed and the caller must not run the tool.

    Fails **open** if the cache is unavailable: this guard exists to stop an
    agent looping, not to be a hard licence check, and taking the whole MCP
    surface offline because Redis blipped would be a worse failure than briefly
    unbudgeted calls. The event is logged so it is visible.
    """
    limit = get_limit()
    window = get_window_seconds()
    key = _key(org_id)

    try:
        # `add` only sets when absent, so it both initialises the counter and
        # starts the window's TTL without clobbering an in-flight window.
        cache.add(key, 0, timeout=window)
        used = cache.incr(key)
    except ValueError:
        # The key expired between `add` and `incr`. Re-seed and count this call
        # as the first of a fresh window.
        cache.set(key, 1, timeout=window)
        used = 1
    except Exception as error:
        logger.error(
            f"MCP spend guard unavailable for org '{org_id}', allowing call: {error}"
        )
        return BudgetState(allowed=True, used=0, limit=limit, window_seconds=window)

    if used > limit:
        # Over budget. The counter is deliberately left incremented: decrementing
        # here would let a caller probe the limit repeatedly at no cost.
        ttl = None
        try:
            ttl = cache.ttl(key)
        except Exception:
            pass
        logger.warning(
            f"MCP billable budget exhausted for org '{org_id}': {used}/{limit}"
        )
        return BudgetState(
            allowed=False,
            used=used,
            limit=limit,
            window_seconds=window,
            retry_after_seconds=ttl,
        )

    return BudgetState(allowed=True, used=used, limit=limit, window_seconds=window)
