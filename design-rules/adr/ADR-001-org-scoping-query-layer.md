# ADR-001: Org scoping is enforced at the query layer

## Context

Multi-tenant data isolation can be enforced at the database (row-level security), in the application's query layer, or in the view layer alone. Postgres RLS would require per-request `SET` calls and would couple the application tightly to one database engine. View-layer-only enforcement relies on every developer remembering to filter — a single missed view leaks cross-tenant data.

## Decision

Org scoping is enforced in the application's query layer through two complementary mechanisms:

1. `DefaultOrganizationManagerMixin` for models with a direct organization FK.
2. `OrgAwareManager` and `OrganizationFilterBackend` for models that reach `Organization` only through a chain of FKs (BFS-discovered).

The thread-local `org_id` is set by `CustomAuthMiddleware` on every request. See `design-rules/security/tenant-isolation.md` for the full layered defense.

## Consequences

- Adding a new tenant model is a one-line manager declaration.
- Code outside a request context (workers, tasks) must explicitly set the org context before issuing queries on tenant models.
- The application is portable across database engines because no RLS feature is used.
