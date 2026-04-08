# account_v2 — Design Rules

`account_v2` owns the tenant-graph root — `Organization`, `User`, and `OrganizationMember`. Every other tenant-scoped model in this repo ultimately resolves to an `Organization` defined here.

> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.

This file follows the [per-component contract](../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).

---

## Scope

|  |  |
|---|---|
| **Covers** | `backend/account_v2/**` — `Organization`, `User`, `OrganizationMember`, their managers, serializers, views, signals, and the auth middleware glue |
| **Excludes** | Usage rollups → [`account_usage`](../account_usage/DESIGN_RULES.md). Tenant-scoped data in other apps → each app's own `DESIGN_RULES.md`. |

## Read first

| File | Why it binds here |
|---|---|
| [`principles.md`](../../design-rules/principles.md) | P1 (org scoping), P2 (credentials), P8 (fail-closed) |
| [`ai-review-checklist.md`](../../design-rules/ai-review-checklist.md) | 9 questions every change must answer |
| [`security/tenant-isolation.md`](../../design-rules/security/tenant-isolation.md) | Three-Layer Defense — `account_v2` owns Layer 1 (middleware) and is the root of Layer 3 (filter backend) |
| [`adr/ADR-001`](../../design-rules/adr/ADR-001-org-scoping-query-layer.md) | Org scoping is enforced at the query layer, not via RLS |

---

## Rules

### R1 — `Organization` is the single root of the tenant graph

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Every tenant-scoped model must resolve to exactly one `Organization`, by direct FK or documented FK chain. A second root would split tenant isolation and break `OrganizationFilterBackend`'s BFS walk. |
| **Refs** | `principles.md#P1` · `security/tenant-isolation.md` · `adr/ADR-001` |
| **Enforced by** | `OrganizationFilterBackend` (Three-Layer Defense, Layer 3) + code review |

### R2 — Active-org resolution always goes through `CustomAuthMiddleware`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | The middleware is Layer 1 of the Three-Layer Defense — it validates the user belongs to the org and stores `org_id` in the thread-local `StateStore`. Reading the org from a header, request param, or cookie directly bypasses validation and is a tenant boundary violation. |
| **Refs** | `principles.md#P8` · `security/tenant-isolation.md` |
| **Enforced by** | `CustomAuthMiddleware` + code review |

### R3 — Org membership has exactly one source of truth: `OrganizationMember`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | A second membership table would let an org/user pair exist in one place and not the other, producing inconsistent authorization decisions and orphaned credentials. Membership is the anchor used by every other app to check whether a user can act inside an org. |
| **Refs** | `principles.md#P1` · `principles.md#P2` |
| **Enforced by** | code review only |

### R4 — Credentials on `User` follow P2 (stored once, referenced by ID)

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Duplicating a credential makes rotation impossible and leaves stale copies behind on member departure. `User`-owned credentials must be referenced by ID from anywhere that consumes them, never copied. |
| **Refs** | `principles.md#P2` |
| **Enforced by** | not yet enforced — see project issue tracker (credential lifecycle) |

---

## Checklist

See [Definition of Done](../../design-rules/definition-of-done.md).
