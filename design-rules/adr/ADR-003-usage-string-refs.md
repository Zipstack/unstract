# ADR-003: Usage uses string references

## Context

Usage records are written for billing and accounting. If those records held a hard FK to `Workflow`, deleting a workflow would either cascade-delete its billing history (data loss) or be blocked entirely (poor UX). Neither is acceptable for records that must outlive the entity they describe (P4).

## Decision

`Usage` stores `workflow_id` as a string reference rather than a FK. The reference points at the workflow but does not enforce referential integrity. Reads that need the workflow object resolve it explicitly.

## Consequences

- Billing rows survive workflow deletion.
- String-reference fields cannot be traced via the BFS-based `OrgAwareManager`. `Usage` therefore relies on a direct `organization` FK for tenant scoping.
- Joins from `Usage` to `Workflow` must be performed explicitly in the application; there is no DB-enforced join path.
