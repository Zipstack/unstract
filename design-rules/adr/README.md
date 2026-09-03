# Architecture Decision Records

This directory contains the **active** Architecture Decision Records for the repository. Proposals, rejected options, and superseded ADRs are not stored here — `git log` is the historical record.

---

## Index

| ADR | Title |
|---|---|
| [ADR-001](ADR-001-org-scoping-query-layer.md) | Org scoping is enforced at the query layer |
| [ADR-002](ADR-002-no-org-fk-on-execution.md) | No org FK on Execution |
| [ADR-003](ADR-003-usage-string-refs.md) | Usage uses string references |
| [ADR-005](ADR-005-prompt-studio-registry-publish-gate.md) | Prompt Studio Registry as the publish gate |
| [ADR-006](ADR-006-organization-rate-limit-separation.md) | OrganizationRateLimit separated from Configuration |
| [ADR-007](ADR-007-adapter-access-runtime-validation.md) | Adapter access validated at runtime |
| [ADR-012](ADR-012-connectorauth-user-owned.md) | ConnectorAuth is owned by User |
| [ADR-014](ADR-014-internal-external-api-separation.md) | Internal and external APIs separated per app |

Numbers are assigned in creation order and **never reused** — gaps in the index signal a removed or superseded ADR.

---

## ADR format

Every active ADR has exactly three sections under the title:

```markdown
# ADR-NNN: <title>

## Context
<the situation and constraints that prompted the decision>

## Decision
<what was decided>

## Consequences
<what becomes easier, harder, or required as a result>
```

There is no `Status` field. The fact that the file exists at this path is what makes it active — the merge IS the acceptance.

---

## Supersession

When an ADR is overturned, the file is **deleted in the same PR** that introduces the replacement. There is no stub, no tombstone, no Status flip.

| Step | Action |
|---|---|
| 1 | Write the new ADR. Its `## Context` section cites the old ADR by ID and explains why the prior decision is being overturned. |
| 2 | Delete the old ADR file in the same PR. |
| 3 | Update every reference to the old ADR ID in the repo — per-component `DESIGN_RULES.md` `Refs` rows, `principles.md`, `security/`, code comments, anywhere — to point at the new ADR. M2 enforces this. |
| 4 | The old ADR's number is never reused. The gap in the index is the only marker that an ADR existed at that number. |

Forensic recovery: `git log --all --diff-filter=D -- design-rules/adr/ADR-NNN-*.md` finds the deletion commit; `git show <commit>^:design-rules/adr/ADR-NNN-*.md` retrieves the original body.

---

## How to add an ADR

| Step | Action |
|---|---|
| 1 | Pick the next free `ADR-NNN` number (the highest existing number plus one — never fill a gap). |
| 2 | Create `ADR-NNN-short-slug.md` using the format above. |
| 3 | Link the ADR from the per-component `DESIGN_RULES.md` of any directory it constrains. |
