# workers/shared — Design Rules

`workers/shared` is the common library imported by every worker under `workers/`. It owns the internal API client used to talk to the backend, HTTP session lifecycle, Celery task wrappers, and the shared config/env surface. Nothing in this directory may import Django — workers run without a Django process.

> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.

This file follows the [per-component contract](../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).

---

## Scope

|  |  |
|---|---|
| **Covers** | `workers/shared/**` — `InternalAPIClient` and its sub-clients, HTTP session management, Celery task base classes, worker-side config/env loading, logging helpers |
| **Excludes** | Individual worker entrypoints → each `workers/<worker>/DESIGN_RULES.md`. Backend-side internal API views → [`backend/api_v2`](../../backend/api_v2/DESIGN_RULES.md) and the `/internal/` url group. Orchestration models → [`backend/workflow_manager`](../../backend/workflow_manager/DESIGN_RULES.md). |

## Read first

| File | Why it binds here |
|---|---|
| [`principles.md`](../../design-rules/principles.md) | P6 (execution org inheritance), P8 (internal vs external) |
| [`ai-review-checklist.md`](../../design-rules/ai-review-checklist.md) | 9 questions every change must answer |
| [`adr/ADR-014`](../../design-rules/adr/ADR-014-internal-external-api-separation.md) | Workers reach the backend through `/internal/...` only |
| [`security/standards.md`](../../design-rules/security/standards.md) | Internal API network isolation, `InternalAPIAuthMiddleware`, Celery serialization |

---

## Rules

### R1 — All backend traffic goes through `InternalAPIClient`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Every worker-to-backend call must use `InternalAPIClient` (or one of its sub-clients under `workers/shared/clients/`). Ad-hoc `requests.get(...)` against public REST endpoints bypasses the internal auth boundary, the shared session pool, and retry/backoff policy, and makes worker behaviour depend on end-user auth middleware. |
| **Refs** | `principles.md#P8` · `adr/ADR-014` · `security/standards.md` (Internal API network isolation) |
| **Enforced by** | code review only |

### R2 — Workers authenticate with the internal service key, never user credentials

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Worker-to-backend traffic is authenticated by `InternalAPIAuthMiddleware` using the shared internal service key, which is distinct from end-user auth. Embedding a user's session token, API key, or credentials in a worker request conflates the identities and turns a worker bug into an auth-escalation path. |
| **Refs** | `principles.md#P8` · `security/standards.md` (`InternalAPIAuthMiddleware`) |
| **Enforced by** | `InternalAPIAuthMiddleware` (backend side) + code review |

### R3 — `workers/shared` must not import Django

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Workers run in Docker images without a Django process. Importing `django.*`, Django models, or Django settings from `workers/shared` turns every worker into a Django dependency and defeats the whole purpose of the new workers architecture (the system must work with AND without the new workers). Data coming from the backend must be consumed as JSON payloads and mapped into local dataclasses. |
| **Refs** | `principles.md#P6` · `CLAUDE.md` (architecture principles) |
| **Enforced by** | code review only |

### R4 — Celery task signatures are JSON-serializable only

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Workers accept JSON only; `pickle` is disabled. Every task argument and return value must be JSON-serializable — pass IDs, dataclass `asdict()` output, or plain primitives. Passing Django model instances or arbitrary Python objects will fail at the broker boundary and regress the pickle lockdown. |
| **Refs** | `security/standards.md` (Celery serialization) |
| **Enforced by** | Celery broker config (`task_serializer = "json"`) + code review |

### R5 — HTTP sessions are lifecycle-managed and closed on worker shutdown

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | `InternalAPIClient` uses a `requests.Session` with a connection pool sized by `API_CLIENT_POOL_SIZE`. Sessions must be closed idempotently (`_closed` flag), honoured in `try/finally` around task bodies that own a client, and the singleton must be reset in `on_worker_process_shutdown`. Leaking sessions leaks socket FDs in long-running workers (UNS-205). |
| **Refs** | `principles.md#P4` (durability/reliability) |
| **Enforced by** | `workers/shared/tests/test_session_lifecycle.py` + code review |

### R6 — Org context is read from the task payload, not from thread-local state

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Workers have no `CustomAuthMiddleware` and no `StateStore` thread-local populated by request processing. Task functions must receive `organization_id` (or a parent entity ID that the backend will resolve to an org) as an explicit argument. Inferring org from a global or "current" variable inside worker code is unsafe and breaks P6 execution org inheritance. |
| **Refs** | `principles.md#P6` · `principles.md#P1` |
| **Enforced by** | code review only |

---

## Known Exceptions

None.

## Checklist

See [Definition of Done](../../design-rules/definition-of-done.md).
