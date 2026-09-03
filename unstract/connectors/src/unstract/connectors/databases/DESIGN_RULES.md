# databases — Design Rules

This subtree contains every database connector shipped with Unstract: PostgreSQL, BigQuery, Snowflake, MSSQL, MySQL, MariaDB, Oracle, and Redshift. Each connector builds SQL against tenant data, so every change here is a potential SQL-injection surface and must follow the SQL Safety Standard (S1).

> **Compatibility:** All changes to this component must remain compatible with extension by an external layer that runs this codebase alongside additional Django applications sharing the same database.

This file follows the [per-component contract](../../../../../../design-rules/per-component-contract.md) (rule format, severity vocabulary, Known Exceptions, M1/M2/M3 meta-rules).

---

## Scope

|  |  |
|---|---|
| **Covers** | `unstract/connectors/src/unstract/connectors/databases/**` — every supported database connector, its query builders, its identifier/quoting helpers, and its error surfaces |
| **Excludes** | Filesystem connectors → `unstract/connectors/src/unstract/connectors/filesystems/`. Queue connectors → `unstract/connectors/src/unstract/connectors/queues/`. Parent connector framework rules → [`unstract/connectors/DESIGN_RULES.md`](../../../../DESIGN_RULES.md). |

## Read first

| File | Why it binds here |
|---|---|
| [`principles.md`](../../../../../../design-rules/principles.md) | P2 (credentials) — DSN/auth handling |
| [`ai-review-checklist.md`](../../../../../../design-rules/ai-review-checklist.md) | 9 questions every change must answer |
| [`security/standards.md`](../../../../../../design-rules/security/standards.md) | **S1 — SQL Safety Standard**, which this file specialises for the databases subtree |
| [`unstract/connectors/DESIGN_RULES.md`](../../../../DESIGN_RULES.md) | Parent connector framework rules also apply — load both |

---

## Rules

### R1 — External identifiers are validated before use in SQL

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Any identifier (table name, column name, schema) that originates outside the function must pass `validate_identifier` before appearing in a SQL string. Without validation, a caller can smuggle arbitrary SQL through what the connector assumes is a name. |
| **Refs** | `security/standards.md#S1` (rule 1) |
| **Enforced by** | code review only |

### R2 — Validated identifiers are quoted via the engine's `QuoteStyle`

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Different engines require different quote characters (`"`, `` ` ``, `[...]`). Validated identifiers must be quoted with `quote_identifier` using the DB-specific `QuoteStyle`. Hard-coding a quote character in a per-connector helper breaks on the next engine that doesn't use it and tempts copy-paste SQL assembly. |
| **Refs** | `security/standards.md#S1` (rule 2) |
| **Enforced by** | code review only |

### R3 — Values are always passed as bound parameters

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | All values must be passed through the DB driver as bound parameters. Never interpolate a value into the SQL string, even if it "looks safe" (numeric, enum, internal). The driver's parameter handling is the only boundary we trust. |
| **Refs** | `security/standards.md#S1` (rule 3) |
| **Enforced by** | code review only |

### R4 — SQL is never assembled with f-strings or `%`-formatting on user input

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | f-strings and `%`-formatting with user input are the canonical path to SQL injection. Identifier substitution is only legitimate after R1 (validation) and R2 (quoting); value substitution always goes through R3. There is no third path. |
| **Refs** | `security/standards.md#S1` (rule 4) · ci: `ruff S608` |
| **Enforced by** | `ruff S608` (hardcoded-sql-expression) + code review |

### R5 — Errors returned to callers strip raw SQL and raw user identifiers

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Error messages that echo the failing SQL or the raw user-supplied identifier turn a connector error into an information-disclosure channel (schema leakage, injection feedback). Errors surfaced to callers must redact both. |
| **Refs** | `security/standards.md#S1` (rule 5) |
| **Enforced by** | code review only |

### R6 — New database connectors implement S1 from day one

|  |  |
|---|---|
| **Severity** | MUST |
| **Why** | Adding a new engine without wiring it through `validate_identifier` + `quote_identifier` + bound parameters regresses S1 by omission. A new connector PR that doesn't exercise the shared helpers is a blocker, even if the engine "happens to" be safe for the specific query shape being added. |
| **Refs** | `security/standards.md#S1` |
| **Enforced by** | code review only |

---

## Checklist

See [Definition of Done](../../../../../../design-rules/definition-of-done.md).
