# Security Standards

These standards describe currently implemented protection patterns. New code must follow them.

---

## S1 — SQL Safety Standard

|  |  |
|---|---|
| **Applies to** | All database connectors in `unstract/connectors/.../databases/`. |
| **Supported set** | PostgreSQL · BigQuery · Snowflake · MSSQL · MySQL · MariaDB · Oracle · Redshift |

Rules:

1. **Identifier validation.** Any identifier (table name, column name, schema) that comes from outside the function must be validated by `validate_identifier` before being used in SQL.
2. **Identifier quoting.** Validated identifiers must be quoted with `quote_identifier` using the DB-specific `QuoteStyle`. Different engines require different quote characters; never hard-code `"` or `` ` ``.
3. **Parameterized values.** All values must be passed as bound parameters through the DB driver. Never interpolate values into the SQL string.
4. **No f-string SQL.** SQL strings must not be assembled with f-strings or `%`-formatting using user input. Identifier substitution is only allowed after validation+quoting (rule 1+2).
5. **Error message hygiene.** Error messages returned to callers must not include raw SQL or raw identifier values from user input.

These rules apply to every supported database connector.

---

## Other current protection patterns

| Pattern | Description |
|---|---|
| **`EncryptedBinaryField`** | Used for `ConnectorInstance.connector_metadata` (P2). |
| **CSP, CORS, CSRF, X-Frame-Options** | Middleware are enabled in the backend Django settings. |
| **File upload validation** | Uploaded documents are validated for MIME type (PDF) and bounded to a 200 MB size limit. |
| **Internal API network isolation** | Internal endpoints live under a separate URL group and require `InternalAPIAuthMiddleware`. They must not be exposed to the public network. |
| **`InternalAPIAuthMiddleware`** | Authenticates service-to-service traffic with a shared secret distinct from end-user auth. |
| **Celery serialization** | Workers accept JSON only. `pickle` and equivalents are disabled. |
| **Django admin disabled by default** | In production settings. |
| **Dependabot** | Configured for dependency updates. |
