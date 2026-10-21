"""Shared test object factories for the Agent-KV suites."""

from account_v2.models import Organization

from agent_kv.models import AgentKVKey


def kv_key(*, slug: str = "acme-slug", org_pk: int = 1, **overrides) -> AgentKVKey:
    """A USABLE AgentKVKey — one that carries an organization.

    `AgentKVKey.organization` is nullable on the model, but a key without one is
    not usable: every downstream consumer is org-scoped (the subscription gate,
    the concurrency limiter, the storage prefix, every job lookup), so
    `AgentKVKeyValidator` refuses it. Tests that build a bare
    `AgentKVKey(name=...)` are therefore constructing a key the auth layer would
    reject, and any behaviour they assert past that point is unreachable in
    production.

    `org_pk` and `slug` are deliberately DIFFERENT kinds of value:
    `Subscription.organization_id` is a CharField holding the slug, while the
    key's own `organization_id` is the FK primary key. Keeping them distinct is
    what lets a test catch code that reaches for the wrong one.
    """
    key = AgentKVKey(name="k", is_active=True, **overrides)
    key.organization = Organization(id=org_pk, organization_id=slug)
    return key
