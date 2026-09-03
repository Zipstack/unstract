# connectors — Design Rules

`unstract/connectors` is the connector framework shared by the backend and workers. It defines the base classes (`UnstractConnector`, the connectorkit registry, exceptions, connection types) and ships three connector families as subtrees: `filesystems/`, `databases/`, and `queues/`. Every concrete connector plugs into this framework and inherits its credential handling, registration, and error contract.

> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.

This file follows the [per-component contract](../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).

---

## Scope

|  |  |
|---|---|
| **Covers** | `unstract/connectors/**` — base classes, `connectorkit` registry, exceptions, connection-type enums, and the shared credential/metadata handling applied to every connector family |
| **Excludes** | SQL-specific rules for database connectors → [`databases/DESIGN_RULES.md`](src/unstract/connectors/databases/DESIGN_RULES.md). Filesystem-specific rules live (or will live) in the filesystems subtree. Backend-side `ConnectorInstance` model and its viewsets → [`backend/connector_v2`](../../backend/connector_v2/DESIGN_RULES.md). |

## Read first

| File | Why it binds here |
|---|---|
| [`principles.md`](../../design-rules/principles.md) | P2 (credentials), P5 (fail-closed) |
| [`ai-review-checklist.md`](../../design-rules/ai-review-checklist.md) | 9 questions every change must answer |
| [`security/standards.md`](../../design-rules/security/standards.md) | `EncryptedBinaryField` on `ConnectorInstance.connector_metadata`, SQL Safety Standard (S1) for the databases subtree |

---

## Rules

### R1 — Persisted connector credentials go through `EncryptedBinaryField`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Connector credentials (DSN, OAuth tokens, service-account JSON, bucket keys) are persisted on `ConnectorInstance.connector_metadata` and must be stored via `EncryptedBinaryField`. Writing a plaintext credential to the database breaks P2 and leaves a stale copy even after rotation. |
| **Refs** | `principles.md#P2` · `security/standards.md` (`EncryptedBinaryField`) |
| **Enforced by** | `EncryptedBinaryField` (backend-side) + code review |

### R2 — Credentials never appear in logs or error messages

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Raw credentials, DSN strings, and token values must not be logged, included in exception messages, or echoed to callers. A traceback that leaks a credential is an information-disclosure bug, and every connector is on this boundary. Redact at the point of raise, not at the logging sink. |
| **Refs** | `principles.md#P2` · `security/standards.md` |
| **Enforced by** | code review only |

### R3 — Every connector registers through the `connectorkit` registry

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Concrete connectors are discovered and instantiated through `connectorkit`. Side-channel instantiation (direct `from unstract.connectors.databases.foo import Foo`) bypasses the registry, loses the shared credential/metadata handling, and makes the connector invisible to the admin/listing endpoints. |
| **Refs** | `principles.md#P5` |
| **Enforced by** | code review only |

### R4 — Connector errors surface as the framework's exception hierarchy

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Driver-level exceptions (`psycopg2.*`, `google.api_core.*`, `boto3.ClientError`, …) must be wrapped in the `unstract.connectors.exceptions` hierarchy before leaving the connector. Callers depend on a stable error contract to distinguish retryable, auth, and misconfiguration failures — leaking the raw driver exception couples callers to the driver and defeats retry/backoff policy. |
| **Refs** | `security/standards.md` |
| **Enforced by** | code review only |

### R5 — Database connectors inherit the SQL Safety Standard from `databases/`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | The databases subtree is governed by [`databases/DESIGN_RULES.md`](src/unstract/connectors/databases/DESIGN_RULES.md), which specialises S1 for this framework (identifier validation, quoting, bound parameters, no f-string SQL, error hygiene). Any change that touches SQL assembly in this framework — including base classes or helpers that a database connector will call — must be reviewed against those rules in addition to the ones in this file. |
| **Refs** | `security/standards.md#S1` · `databases/DESIGN_RULES.md` R1–R6 |
| **Enforced by** | code review only |

---

## Checklist

See [Definition of Done](../../design-rules/definition-of-done.md).
