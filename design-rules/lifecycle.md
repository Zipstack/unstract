# Change Lifecycle

A change moves through five phases. Each phase has its own checks.

---

## 1. Design

|  |  |
|---|---|
| **Check** | State the principle(s) the change relies on (link to [`principles.md`](principles.md)). |
| **Check** | If the change introduces a new model relationship, identify the org path: direct FK, BFS-discoverable parent chain, or anchor entity (P9). |
| **Check** | If the change introduces a new ADR-worthy decision, draft the ADR before coding. |

---

## 2. Assembly

|  |  |
|---|---|
| **Check** | Apply the per-component `DESIGN_RULES.md` of every directory the change touches. |
| **Check** | Run the AI Review Checklist mentally as you write each commit. |
| **Check** | Migrations: never widen tenant visibility. Never break the org scoping path. |

---

## 3. Deploy

|  |  |
|---|---|
| **Check** | Internal endpoints stay behind `InternalAPIAuthMiddleware` (P8). |
| **Check** | External endpoints stay behind the configured auth middleware (P5). |
| **Check** | Celery tasks use JSON serialization only. |

---

## 4. Runtime

|  |  |
|---|---|
| **Check** | Adapter access is validated at the moment of execution (ADR-007). |
| **Check** | Org context is set by `CustomAuthMiddleware` and read from thread-local state by managers and filter backends. |

---

## 5. Monitoring

|  |  |
|---|---|
| **Check** | Usage and audit-style writes are durable across source-object deletion (P4). |
| **Check** | Logs from execution carry workflow and execution identifiers; org is derived through the workflow chain (P6). |
