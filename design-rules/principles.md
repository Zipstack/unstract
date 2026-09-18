# Principles P1–P9

These nine principles govern every change in this repository. They describe rules new code must follow. Existing code that violates a principle is wrong and should be flagged in review.

> **Severity.** Every principle is **MUST** unless a per-component `DESIGN_RULES.md` explicitly weakens it via a rule with `Severity: SHOULD` or `MAY` and a documented `Why`.

Principles are referenced from per-component files via `principles.md#PN` (e.g. `principles.md#P1`). Update those references whenever a principle is renumbered.

---

## P1 — Organization scoping is mandatory

|  |  |
|---|---|
| **Rule** | Every model that holds tenant data must be reachable from `Organization` and must be filtered by the requesting user's organization on every read and write. |
| **Implementation** | Tenant models with a direct `organization` FK use `DefaultOrganizationMixin` (model mixin — adds the FK and auto-populates it on save) together with `DefaultOrganizationManagerMixin` (manager mixin — filters every queryset by the current org). Models that reach `Organization` only through a parent FK chain use `OrgAwareManager` or rely on `OrganizationFilterBackend` (the view-layer backend that BFS-walks the FK chain). See [`security/tenant-isolation.md`](security/tenant-isolation.md) for the full Three-Layer Defense. |
| **Example** | A new model that stores documents must add a direct `organization` FK or a path that BFS-resolves to one. A new DRF view on a tenant model must inherit the project's filter backend so cross-org reads are impossible. |

---

## P2 — Credentials are encrypted at rest

|  |  |
|---|---|
| **Rule** | Any field that stores third-party credentials, tokens, or secrets must be encrypted at rest. |
| **Implementation** | `EncryptedBinaryField` is used for `ConnectorInstance.connector_metadata`. New credential fields must use the same field type. |
| **Example** | A new connector that stores an API key must place that key inside the encrypted metadata field, never a plain `CharField`. |

---

## P3 — Publishing is an explicit gate

|  |  |
|---|---|
| **Rule** | Authoring artifacts (e.g. Prompt Studio projects) and the runtime artifacts derived from them are separate. Publishing is the explicit gate that turns a draft into a runnable artifact. |
| **Implementation** | See [`adr/ADR-005`](adr/ADR-005-prompt-studio-registry-publish-gate.md): Prompt Studio publishes to `PromptStudioRegistry`; runtime consumers read the registry, never the draft. |
| **Example** | A new authoring surface must not be referenced directly by an executor — it must publish to a registry first. |

---

## P4 — Audit and billing data is append-only in spirit

|  |  |
|---|---|
| **Rule** | Records used for usage accounting, billing, or audit must be written in a way that survives the deletion of the source object they describe. |
| **Implementation** | See [`adr/ADR-003`](adr/ADR-003-usage-string-refs.md): `Usage` uses string references to workflow identifiers so that billing rows survive workflow deletion. |
| **Example** | A new metric model must not put a hard FK to an entity that may be deleted if the metric still needs to exist after deletion. |

---

## P5 — Fail closed on permission decisions

|  |  |
|---|---|
| **Rule** | Any permission, access, or feature gate must default to deny when its inputs are missing or ambiguous. |
| **Implementation** | Middleware that derives org context returns 401/403 when the org cannot be resolved. Auth backends raise rather than silently authorising. |
| **Example** | A new view must never assume "if no org filter, return all rows". |

---

## P6 — Execution inherits org from its parent entity

|  |  |
|---|---|
| **Rule** | Execution-time entities derive their organization from the workflow they run, not from their own FK to organization. |
| **Implementation** | See [`adr/ADR-002`](adr/ADR-002-no-org-fk-on-execution.md): `WorkflowExecution` has no direct `organization` FK; org is derived through `Workflow`. `OrganizationFilterBackend` handles the BFS chain. |
| **Example** | A new execution-side model should not duplicate `organization_id` — it should rely on the parent workflow. |

---

## P7 — Deployments are triggers, not data

|  |  |
|---|---|
| **Rule** | A deployment record (pipeline, schedule, API binding) describes how to invoke a workflow. It does not duplicate the workflow's data. |
| **Implementation** | `pipeline_v2` and `scheduler` hold trigger metadata only. |
| **Example** | A new pipeline type must not snapshot workflow steps — it must reference the workflow. |

---

## P8 — Internal and external surfaces are separated

|  |  |
|---|---|
| **Rule** | Service-to-service APIs and end-user APIs live on separate URL groups, use separate auth, and never share the same view function. |
| **Implementation** | See [`adr/ADR-014`](adr/ADR-014-internal-external-api-separation.md): each app exposes `urls.py` for external and `internal_urls.py` + `internal_views.py` for service-to-service. The internal surface is protected by `InternalAPIAuthMiddleware`. |
| **Example** | A worker calling the backend must hit `/internal/...`, never the user-facing REST API. |

---

## P9 — Anchor entities define the org boundary

|  |  |
|---|---|
| **Rule** | Some entities are *anchors* — canonical owners of an organization's data graph. The most important anchor in this codebase is `Workflow`. Models that hang off an anchor inherit org via that anchor. |
| **Implementation** | `Workflow` is the anchor for execution, file execution, execution logs, tool instances, and prompt registry consumers. |
| **Example** | A new model that belongs to a workflow should derive org through the workflow, never via a parallel direct FK. |
