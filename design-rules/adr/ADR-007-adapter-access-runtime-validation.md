# ADR-007: Adapter access validated at runtime

## Context

Adapter access (which user/org may use which LLM, embedding, or vector store adapter) could be validated only at the moment a workflow is created. But access can be revoked between creation and execution. Validating only at creation time would leave revoked workflows still able to run.

## Decision

Adapter access is validated at the moment of execution. The executor checks, for each adapter the workflow needs, whether the requesting org currently has access. If not, the run is rejected.

## Consequences

- Revoking adapter access immediately stops new runs from using that adapter.
- The executor pays a small per-run validation cost.
- This is the runtime arm of P5 (fail closed): a missing or revoked grant means the run is denied.
