# Tenant Isolation — Three-Layer Defense

Tenant isolation in this codebase is enforced by three independent layers in the Django backend. Every layer must remain in place; removing any one of them is a regression.

---

## Layer 1 — Middleware

|  |  |
|---|---|
| **Component** | `CustomAuthMiddleware` |
| **Behaviour** | Validates the request's identity, resolves the active organization from the session/platform key, and stores the resolved `org_id` in a thread-local `StateStore`. Downstream model managers and filter backends read the org id from this store. |
| **Fail mode** | Rejects the request with 403 when the request targets a specific organization (`request.organization_id` is set on the URL) and the session cannot be resolved to that org. Requests that do not target a specific organization are allowed through with no org set in `StateStore`, and are then fail-closed at Layer 2/3 when they touch tenant data. Layer 1 is *identity-and-binding*, not the primary fail-closed boundary — that role belongs to Layer 3 below (P5). |

---

## Layer 2 — Model Managers

Two complementary mechanisms cover the two FK shapes:

|  |  |
|---|---|
| **`DefaultOrganizationManagerMixin`** | For models that have a direct `organization` FK. The mixin filters every queryset by the org id from thread-local state. |
| **`OrgAwareManager`** | For models without a direct FK. It performs a breadth-first search over the model's relations to find a path to `Organization` and filters via that path. Any model whose manager inherits from `OrgAwareManager` is automatically scoped. |

String-reference fields (e.g. `Usage.workflow_id`, `ToolInstance.tool_id`) cannot be traced via BFS — those models rely on a direct org FK or a separate FK path.

Example use:

```python
class MyModel(models.Model):
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE)

    objects = OrgAwareManager()  # BFS finds Workflow → Organization
```

---

## Layer 3 — Filter Backend

|  |  |
|---|---|
| **Component** | `OrganizationFilterBackend` |
| **Configured in** | `DEFAULT_FILTER_BACKENDS` |
| **Behaviour** | For DRF views over models without a direct org FK, the backend BFS-discovers the chain (e.g. `ExecutionLog → WorkflowExecution → Workflow → Organization`) and applies the filter at the view layer. |

Models currently covered by the filter backend include:

| Model |
|---|
| `WorkflowExecution` |
| `WorkflowFileExecution` |
| `ExecutionLog` |
| `APIKey` |
| `ToolStudioPrompt` |
| `ProfileManager` |
| `IndexManager` |
| `DocumentManager` |

---

## Rules for new code

1. New tenant models must opt into one of the two manager mechanisms.
2. New DRF viewsets over tenant models must rely on the configured filter backend; do not bypass it with raw querysets.
3. Never derive org from request body input — always from the thread-local set by middleware.
