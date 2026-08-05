# ADR-002: No org FK on Execution

## Context

`WorkflowExecution` is created every time a workflow runs. A direct `organization` FK on `WorkflowExecution` would duplicate information already encoded in `Workflow.organization` and create two sources of truth that could drift.

## Decision

`WorkflowExecution` does not carry an `organization` FK. Its organization is derived through `Workflow`. The `OrganizationFilterBackend` BFS-discovers the chain `WorkflowExecution → Workflow → Organization` and applies the org filter at the view layer.

## Consequences

- One source of truth for an execution's organization.
- Cross-org listing of executions requires no special case — the filter backend handles it.
- Any worker that creates an execution must do so via a workflow it has already resolved in the user's org context.
- A model that hangs off `WorkflowExecution` (e.g. `WorkflowFileExecution`, `ExecutionLog`) inherits org through the same chain.
