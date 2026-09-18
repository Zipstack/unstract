# workflow_manager — Design Rules

`workflow_manager` owns `Workflow`, `WorkflowExecution`, `WorkflowFileExecution`, `ExecutionLog`, and the orchestration that runs workflows. `Workflow` is the anchor entity (P9) for the execution-side data graph.

> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.

This file follows the [per-component contract](../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).

---

## Scope

|  |  |
|---|---|
| **Covers** | `backend/workflow_manager/**` — `Workflow`, `WorkflowExecution`, `WorkflowFileExecution`, `ExecutionLog`, their managers, serializers, viewsets, signals, and the orchestration that runs workflows |
| **Excludes** | Tenant-graph root (`Organization`, `User`, `OrganizationMember`) → [`account_v2`](../account_v2/DESIGN_RULES.md). Pipeline/API deployment triggers → [`pipeline_v2`](../pipeline_v2/DESIGN_RULES.md), [`api_v2`](../api_v2/DESIGN_RULES.md). Tool instance config → [`tool_instance_v2`](../tool_instance_v2/DESIGN_RULES.md). |

## Read first

| File | Why it binds here |
|---|---|
| [`principles.md`](../../design-rules/principles.md) | P1 (org scoping), P4 (audit durability), P6 (execution org inheritance), P9 (anchor entity) |
| [`ai-review-checklist.md`](../../design-rules/ai-review-checklist.md) | 9 questions every change must answer |
| [`security/tenant-isolation.md`](../../design-rules/security/tenant-isolation.md) | Three-Layer Defense — execution-side viewsets live on Layer 3 |
| [`adr/ADR-002`](../../design-rules/adr/ADR-002-no-org-fk-on-execution.md) | Execution-side models must not carry a direct `organization` FK |

---

## Rules

### R1 — `Workflow` is the anchor entity for the execution-side data graph

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Every execution-side model (`WorkflowExecution`, `WorkflowFileExecution`, `ExecutionLog`) must derive org through `Workflow` rather than duplicating `organization_id`. A parallel direct FK would split tenant isolation and let the two paths disagree. |
| **Refs** | `principles.md#P6` · `principles.md#P9` · `adr/ADR-002` |
| **Enforced by** | `OrganizationFilterBackend` (BFS walk) + code review |

### R2 — Execution-side viewsets scope reads through `OrganizationFilterBackend`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Bypassing the filter backend with raw querysets (`.objects.all()`, `.objects.filter(workflow__id=...)` without org scoping) opens a tenant-isolation hole. The filter backend is Layer 3 of the Three-Layer Defense and is the single place where org scoping is enforced at the query layer. |
| **Refs** | `principles.md#P1` · `security/tenant-isolation.md` · `adr/ADR-001` |
| **Enforced by** | `OrganizationFilterBackend` + code review |

### R3 — `on_delete` on Workflow-rooted FKs is audit-durable

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | `WorkflowExecution`, `WorkflowFileExecution`, `ExecutionLog`, and usage rollups are audit-style records and must survive deletion of their source `Workflow` until the retention window expires. A `CASCADE` that wipes execution history on workflow deletion violates P4. Models are the source of truth for cascade behaviour — verify via `grep on_delete` on the PR diff rather than a separate list. |
| **Refs** | `principles.md#P4` · `ai-review-checklist.md` (question 4) |
| **Enforced by** | code review only |

### R4 — Deployments and schedules reference the workflow, never copy it

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | `Pipeline`, `APIDeployment`, and scheduled triggers are trigger records — they must hold a FK to `Workflow` and re-read its definition at execution time, not snapshot its fields. Copying would let a running deployment diverge from its source workflow silently. |
| **Refs** | `principles.md#P7` |
| **Enforced by** | code review only |

### R5 — Celery tasks in this component use JSON serialization only

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Workers accept JSON only; `pickle` and equivalents are disabled. Task signatures and arguments must be JSON-serializable. This is also what lets workers communicate with the orchestration across the new workers architecture without Django imports. |
| **Refs** | `security/standards.md` (Celery serialization) · `principles.md#P8` |
| **Enforced by** | Celery broker config (`task_serializer = "json"`) + code review |

---

## Checklist

See [Definition of Done](../../design-rules/definition-of-done.md).
