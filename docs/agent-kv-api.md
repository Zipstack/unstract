# Agent-KV API

Agent-KV is Unstract's agentic key-value extraction product: upload a document plus a
`keys.json`-style extraction schema, get back a job id, poll a verbose agent-centric
status document, and fetch a rich result (record + per-field QA/challenger audit
trail).

This document describes the API **as built in this repo** — the OSS scaffold (routes,
validation, dispatch, job lifecycle, key management). The document, `keys.json` schema,
and OCR/LLM extraction pipeline itself are described only insofar as they shape the
contract; the extraction engine ships as a cloud executor plugin (see
[§11, 501 behavior](#11-when-the-engine-is-unavailable-501-behavior) below).

Design background: `docs/superpowers/specs/2026-08-28-agent-kv-api-design.md` (referred
to as "the spec" throughout this document; section numbers below are spec section
numbers). This document records what shipped, including a handful of places where the
implementation is more specific than — or diverges from — the spec's sketch. Those are
called out explicitly rather than silently reconciled.

## 1. Authentication

There are two independent auth schemes on two different URL prefixes:

| Surface | Prefix | Auth |
|---|---|---|
| Public execution API (submit/status/result/cancel/validate) | `/agent-kv/…` (top-level, not under the tenant subfolder) | `Authorization: Bearer <AgentKVKey>` — a dedicated per-organization key, validated by the view itself |
| Key management (create/list/rotate/revoke) | `{PATH_PREFIX}/unstract/…/agent-kv/keys/…` (tenant-scoped, alongside Platform API key management) | Session auth, `IsOrganizationAdmin` only |

The execution prefix (`AGENT_KV_PATH_PREFIX`, default `agent-kv`) sits **outside** the
tenant-subfolder/organization-middleware chain — it is added to `WHITELISTED_PATHS` in
`backend/backend/settings/base.py` — because a caller authenticates with an API key, not
a session/org header. Every view under it therefore owns its own auth via the
`AgentKVKeyValidator.validate_api_key` decorator (`backend/agent_kv/key_validator.py`),
which:

1. Requires `Authorization: Bearer <key>` where `<key>` is a UUID.
2. Looks up an active (`is_active=True`) `AgentKVKey` by that UUID.
3. Injects the resolved key object as `agent_kv_key` into the view kwargs, which every
   subsequent lookup filters by (`organization_id=agent_kv_key.organization_id`) — this
   is what makes a job in another org indistinguishable from an unknown job id (both
   404, see [Status](#4-status--get-agent-kvjob_id)).

**Drift from the spec:** spec §6.1 describes this as "every endpoint 401s without a
valid key." The implementation returns **403** (`api_v2.exceptions.Forbidden`, reused
as-is rather than adding a new exception class) for both a missing/malformed
`Authorization` header and an unknown/inactive key. This is exercised directly by
`backend/agent_kv/tests/test_auth.py` and `test_job_views.py::test_all_job_views_401_without_key`
(the test name predates the code's actual status; both assert `403`). Document the code:
**403, not 401**, for any auth failure on the public prefix.

Key management (`backend/agent_kv/views.py`, `AgentKVKeyViewSet`) is a standard DRF
`ModelViewSet` scoped by the global `OrganizationFilterBackend` and gated by
`IsOrganizationAdmin` (`backend/agent_kv/permissions.py`). Fields returned:
`id, name, description, key, is_active, created_at`; write-side fields are
`name, description, is_active` only (`key` and `id` are server-generated). Routes
(`backend/agent_kv/urls.py`, mounted at `agent-kv/` under
`backend/backend/urls_v2.py`):

```
GET/POST    .../agent-kv/keys/
GET/PATCH/DELETE .../agent-kv/keys/<uuid:pk>/
POST        .../agent-kv/keys/<uuid:pk>/rotate/     # replaces `key` with a new UUID
```

Key storage follows the same conventions as Platform API key management (D5) —
plaintext-at-rest UUID keys, not hashed-at-rest; that hardening is explicitly deferred,
not a v1 gap unique to this feature.

## 2. The extraction schema (`keys` field)

The `keys` submit field — spec-called "keys.json" — is a JSON object describing what to
extract. It compiles through `unstract.agent_kv_schema.compile_schema`
(`unstract/agent-kv-schema/src/unstract/agent_kv_schema/`), the **single schema compiler
in the system**: the OSS API validates with it at submit time and at `/validate`, and
the cloud engine imports the same package to execute — the schema language cannot drift
between validation and execution by construction (spec §5.1).

### Node types

A schema node is one of three shapes, decided structurally:

- **Interior node** — every value is itself an object → its keys are child nodes, and
  nesting continues (dotted path, e.g. `vendor.address.city`).
- **Leaf node** — no value is an object → defined by scalar attributes:

  | Attribute | Required | Meaning |
  |---|---|---|
  | `description` | **yes** | Prompted to the extractor; also fed to the breadcrumb-prefixed `effective_description`. |
  | `format` | no (default `string`) | `string` \| `number` \| `currency` \| `date` \| `enum:v1,v2,…` \| `regex:<pattern>` \| any other free-text hint. `number`/`currency` parse via a strip-then-`float()` check; `date` accepts a fixed set of common formats; `enum` matches case-insensitively; `regex` is `re.fullmatch`. |
  | `required` | no (default `false`) | Completeness is checked separately from format. |
  | `aliases` | no (default `[]`) | Alternate names/labels to help the extractor recognize the field. |
  | `multivalued` | no (default `false`) | Value is a comma-separated string; each element is format-checked independently. |

  A node mixing object values and scalar attributes is a **compile-time error**
  ("mixes object children and scalar attributes"), as is a leaf with unknown attribute
  keys or a missing `description`.

- **Array node** — has an `_array` key → a flat (non-nested) row schema:

  ```json
  "line_items": {
    "description": "One row per invoice line",
    "_key": "sku",
    "_array": {
      "sku": {"description": "SKU"},
      "total": {"description": "Line total", "format": "currency"}
    }
  }
  ```

  `_array`'s value is itself a flat object of leaf columns (row-local paths, not
  dotted). `description` is optional context; `_key` (optional) names a column used for
  row identity in downstream scoring, otherwise rows are matched positionally. A
  nested array inside an array's row schema is rejected at compile time ("not supported
  in P8a") — arrays are single-level only in v1.

### Constraints (`_constraints`)

An optional top-level `_constraints` key: a list of string expressions checked against
the extracted record post-hoc. Each expression is parsed and statically validated
against an AST allowlist before it is ever accepted — no arbitrary code execution:
boolean/comparison/arithmetic operators, plus exactly one string-literal argument to one
of `sum`, `count`, `min`, `max`, `avg` (an array path). Example:
`"count('line_items') >= 1"`.

### Structural caps (spec §6.1)

Enforced by `compile_schema` regardless of the byte-size cap below (`SchemaCaps` in
`compile.py`):

| Cap | Default |
|---|---|
| Max leaves | 200 |
| Max arrays | 20 |
| Max columns per array | 40 |
| Max nesting depth | 6 |
| Max regex pattern length | 200 |
| Max aliases per field | 10 |
| Max description length | 500 |
| Max constraints | 30 |

These caps are hardcoded in the compiler (not env-configurable); what **is**
env-configurable is the raw byte size of the whole `keys` document
(`AGENT_KV_MAX_SCHEMA_BYTES`) and of `calculations`
(`AGENT_KV_MAX_CALCULATIONS_BYTES`) — see [§13 env reference](#13-environment-reference).

A schema that fails to compile is rejected with a `400` at submit time — **nothing is
billed** — or, at `/validate`, with a `200` carrying `{"valid": false, "error": "<message>"}`
(compile errors are not 400s there; only a missing `keys` body key is).

## 3. Submit — `POST /agent-kv/` (multipart)

Copied verbatim from spec §7.1 and cross-checked field-by-field against
`backend/agent_kv/execution_serializers.py::SubmitSerializer` — every row below matches
the shipped serializer exactly; no drift found in the submit contract itself (see the
notes after the table for two spec-vs-code nuances worth flagging).

| Field | Required | Notes |
|---|---|---|
| `file` | yes | One document per job (D12). |
| `keys` | yes | `keys.json` (file part or inline JSON string). Compiled synchronously; invalid ⇒ 400, nothing billed. |
| `document_class` | no | Free-text hint (as CLI). |
| `key_notes` | no | Free-text notes appended to the prompt (as CLI). |
| `calculations` | no | Post-processing instructions; opt-in codegen. Disabled by default; enabled per deployment via `AGENT_KV_CALCULATIONS_ENABLED`. |
| `page_start`, `page_end` | no | 1-based inclusive range. |
| `qa` | no | Default **on**. |
| `challenge` | no | Default **on** (~doubles LLM spend; meter records what ran). |
| `extraction_mode` | no | `whole-doc` (default) \| `per-page`. |
| `structured_output` | no | Disabled by default; enabled per deployment via `AGENT_KV_STRUCTURED_OUTPUT_ENABLED`. |
| `timeout` | no | Omitted or `0` = pure async (immediate 202). `1–300`: the view polls the job row up to the deadline and returns the result inline if the job completes, else 202 with the job id. |
| `tags`, `custom_data` | no | Echoed through. |
| `webhook_url` | no | Terminal-state POST `{job_id, status}` only — no result payload. |

Not exposed (D6): model choice, challenger model, `parallel_pages`, thinking budgets.

**Two implementation-level notes not visible in the table:**

- File type is allowlisted (`.pdf .xlsx .xls .png .jpg .jpeg .tiff`) and size-capped
  (`AGENT_KV_MAX_FILE_SIZE_MB`); PDFs are page-counted **locally, pre-OCR**, via
  `pdfplumber` and rejected over `AGENT_KV_MAX_PAGES` before any paid work runs. Images
  count as 1 page. Excel has no pre-OCR page concept — it is capped by file size only at
  submit time (the engine enforces a post-OCR virtual-page cap).
- `timeout`'s upper bound is not the literal `300` in the spec prose — it's
  `AGENT_KV_MAX_TIMEOUT_SECONDS` (default `300`, but deployment-configurable).

### Response

`202` (async, the default):

```json
{
  "job_id": "5b6e9b0a-...",
  "status": "DISPATCHED",
  "status_url": "/agent-kv/5b6e9b0a-...",
  "created_at": "2026-08-28T10:15:00.123456+00:00"
}
```

`200` (when `timeout` was set and the job finished before the deadline): the full
[result payload](#5-result--get-agent-kvjob_idresult), same shape as the result
endpoint.

`501`: [engine unavailable](#11-when-the-engine-is-unavailable-501-behavior).
`429`: rate-limited (per-key request rate, or per-org concurrent-job limit — see
[§13](#13-environment-reference)).
`400`: serializer/schema validation failure — nothing billed.

### Example

```bash
curl -X POST https://api.unstract.example/agent-kv/ \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345" \
  -F "file=@invoice.pdf" \
  -F 'keys={
        "quotation_number": {"description": "The quote number", "required": true},
        "customer": {"name": {"description": "Bill-to name"}},
        "line_items": {
          "description": "One row per line",
          "_key": "sku",
          "_array": {
            "sku": {"description": "SKU"},
            "total": {"description": "Line total", "format": "currency"}
          }
        },
        "_constraints": ["count(\"line_items\") >= 1"]
      }' \
  -F "challenge=false" \
  -F "webhook_url=https://example.com/hooks/agent-kv"
```

## 4. Status — `GET /agent-kv/{job_id}`

Verbose, agent-centric, stage-level (`backend/agent_kv/execution_views.py::_status_document`).
Stage list (superset; only stages that actually ran for this job appear, in a fixed
order): `document_processing, extraction, qa, challenge, normalize, constraints,
codegen, code_execution`.

```json
{
  "job_id": "5b6e9b0a-...",
  "status": "running",
  "stage": "challenge",
  "stages": [
    {"name": "document_processing", "status": "done", "seconds": 6.2},
    {"name": "extraction", "status": "done", "seconds": 11.4},
    {"name": "qa", "status": "done", "seconds": 4.1},
    {"name": "challenge", "status": "running"}
  ],
  "created_at": "2026-08-28T10:15:00.123456+00:00",
  "started_at": "2026-08-28T10:15:01.500000+00:00",
  "completed_at": null,
  "pages_total": 3
}
```

Each stage entry always carries `status` (`running`|`done`) and, if reported,
`seconds`; any additional flat scalar counters the executor reported for that stage
(e.g. `keys_checked`, `flagged`, `fields_repulled`) ride alongside — nested/list
counters, and any counter using the reserved keys `status`/`seconds`, are dropped by the
internal stage-report endpoint rather than persisted (`backend/agent_kv/internal_views.py::_sanitize_counters`).

`status` is lowercased (`pending`, `dispatched`, `running`, `completed`, `failed`,
`cancelled`); `error` is included (only) when `status == "failed"`. `pages_total` and
`completed_at` are always present (as `null` until known) — an addition beyond the
spec's illustrative example, not a drift, since spec §7.2 was explicitly a partial
sample ("Verbose, agent-centric, stage-level").

```bash
curl https://api.unstract.example/agent-kv/5b6e9b0a-.../ \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 5. Result — `GET /agent-kv/{job_id}/result`

Re-readable until `expires_at` (D11), plus explicit `DELETE`.

- **Non-terminal job** (`PENDING`/`DISPATCHED`/`RUNNING`): `409` with
  `{"status": "<lowercased status>"}`.
- **Expired, or `COMPLETED` with an already-swept/blank `result_ref`**: `404`.
- **`COMPLETED`**: `200` with the engine's full result object, unchanged (record,
  normalized_record, per-field audit trail, `qa_passed`, `challenge_passed`,
  `consistency_violations`, `cost_summary`, `timing` — spec §4; this repo does not
  shape or re-validate that payload, it stores and replays exactly what the executor's
  finalize call sent).
- **`FAILED`**: `200` with
  `{"success": false, "status": "failed", "error": "<user-safe message>"}`.
- **`CANCELLED`**: `200` with `{"success": false, "status": "cancelled"}`.

**Calculation result shape** (when `calculations` is supplied and
`AGENT_KV_CALCULATIONS_ENABLED=true`): a `COMPLETED` result adds these fields to the
engine's standard result object:

- `calculations_applied: true` — indicates calculation codegen ran.
- `execution: {success: bool, rows_written: int, error: string|null}` — sandbox worker
  execution status. `success` is `true` if the generated code ran without error;
  `rows_written` is the count of rows the code emitted; `error` is `null` on success, or
  a user-safe message (e.g., `"Runtime error: division by zero"`) on failure.
- `codegen_validation_passed: bool` — whether the AST gate (layer 1 of a 5-layer
  defense-in-depth model) accepted the generated code syntax.
- `calculation_rows: [...]` — an array of computed JSONL rows (size-capped). If the code
  produced more rows than the cap allows, this array is empty and `calculation_rows_truncated: true`
  is present instead.

If the sandbox worker fails to execute, the job completes with `success: false` and a
user-safe `error` (e.g., `"Calculation execution timed out"`); the `execution` field
carries the inner error details.

**Drift from the spec:** §7.3 sketches the failed-job body as
`{success: false, error, timing}`. The shipped body
(`backend/agent_kv/execution_views_result.py::result_payload`) is
`{"success": false, "status": "failed", "error": ...}` — it adds `status` and does
**not** include a `timing` key (there is nothing to time for a job that never produced
an engine result). Document the code: no `timing` on failure/cancellation bodies.

```bash
curl https://api.unstract.example/agent-kv/5b6e9b0a-.../result \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

```json
{
  "success": true,
  "record": {"quotation_number": "Q-10234", "customer": {"name": "Acme Corp"}},
  "normalized_record": {"quotation_number": "Q-10234", "customer": {"name": "Acme Corp"}},
  "keys": [
    {"key_path": "quotation_number", "qa_status": "pass", "challenge_status": "pass"}
  ],
  "qa_passed": true,
  "challenge_passed": true,
  "consistency_violations": [],
  "cost_summary": {
    "total_cost": 0.0,
    "input_tokens": 3120,
    "output_tokens": 480,
    "agents": {
      "kv_extractor": {"input_tokens": 2400, "output_tokens": 360, "cost": 0.0},
      "kv_qa": {"input_tokens": 720, "output_tokens": 120, "cost": 0.0}
    }
  },
  "timing": {"document_processing": 6.2, "extraction": 11.4}
}
```

**`cost_summary` dollars are always `0.0` and are not a billing figure**: the executor
zeroes the engine's per-token price fields (they were stale hardcoded list prices), so
`total_cost` and every per-agent `cost` come back `0.0` — metering is what bills, from
the SDK's own litellm-priced usage records. Read `cost_summary` for its token/agent
breakdown only. `agents` is omitted entirely when no agent recorded usage (a full
cache hit).

**The per-field audit entries in `keys[]` are keyed `key_path`, not `path`.** A live
entry carries more than the example above shows — this one is verbatim from a real run:
`{"key_path": "invoice_number", "value": "INV-…", "found": true, "qa_status":
"unchecked", "qa_attempts": 0, "line_start": 5, "line_end": 5, "normalized_value":
"INV-…"}` (`qa_status` is `"unchecked"` with `qa_attempts: 0` when the job ran with
`qa=false`).

(The exact result shape beyond `success` is the cloud engine's contract — spec §4 — not
re-specified or validated by this repo.)

## 6. Validate — `POST /agent-kv/validate`

Compile-only check; **free of charge but not free of auth** — authenticated (valid key)
and rate-limited the same as submit (spec §6.1: "an open compile endpoint would be a
probing/DoS surface"). No job is created; nothing is billed either way.

```bash
curl -X POST https://api.unstract.example/agent-kv/validate \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345" \
  -H "Content-Type: application/json" \
  -d '{"keys": {"invoice_number": {"description": "Invoice #", "required": true}}}'
```

Success (`200`):

```json
{"valid": true, "leaves": 1, "arrays": 0, "constraints": 0}
```

Invalid schema — still `200`, not `400` (schema-compile rejection is a *response*, not
a request error):

```json
{"valid": false, "error": "Leaf at invoice_number is missing a 'description'"}
```

Missing `keys` key in the body is the one case that *is* a `400`:
`{"detail": "body must include 'keys'"}`.

## 7. Cancel — `POST /agent-kv/{job_id}/cancel`

Defined precisely per spec §7.4: no task-revocation machinery exists anywhere in the
platform, so cancel flips the job row to `CANCELLED` via the same guarded
`mark_terminal` write gate every other terminalization path uses
(`backend/agent_kv/models.py::AgentKVJob.mark_terminal`) — later callbacks/stage
reports become no-ops; a job not yet picked up is dropped at pickup; a job **already
running continues to completion in the worker** (its LLM spend is still incurred and
metered), its result is simply discarded on arrival. No mid-run abort.

- Won the race (job was non-terminal): `200` `{"status": "cancelled"}`.
- Already terminal: `409` `{"status": "<job.status>"}` — **note this one is the raw
  uppercase enum value** (e.g. `"COMPLETED"`), unlike every lowercased `status` value
  elsewhere in this API (status doc, result 409, validate). This is the code as shipped
  (`execution_views.py::JobCancelView`, confirmed by
  `test_job_views.py::test_cancel_on_completed_is_409_and_result_untouched`), not a
  typo in this document.

```bash
curl -X POST https://api.unstract.example/agent-kv/5b6e9b0a-.../cancel \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 8. Delete — `DELETE /agent-kv/{job_id}`

Deletes the result and any residual staged input immediately, and blanks both refs
(`204`, no body). The job row itself is retained (audit trail); a later `result` fetch
404s (blank `result_ref`), and status still works.

```bash
curl -X DELETE https://api.unstract.example/agent-kv/5b6e9b0a-.../ \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 9. Webhook delivery

`webhook_url` (if given at submit) receives exactly one terminal-state POST:
`{"job_id": "...", "status": "completed"|"failed"|"cancelled"}` — a fixed payload
shape, no result content (spec §6.7, §7.1). Delivered from the `ide_callback` worker
(`workers/ide_callback/agent_kv_tasks.py::_maybe_webhook`) only on a *fresh* finalize
(a duplicate/late finalize for an already-terminal job never re-fires it).

**SSRF controls, as actually implemented** (`workers/shared/utils/webhook_notify.py`,
function `send_webhook`) — this corrects an earlier draft of this document, which
claimed connect-time re-checking and bounded retries; the code does neither, and its
own module docstring says so:

- **Resolution-time check only.** The host is resolved once via `socket.getaddrinfo`
  and every returned address is checked against private/loopback/link-local/
  reserved/multicast/unspecified ranges *before* the request is made
  (`_host_is_public`). It is **not** re-checked at connect time — the subsequent
  `requests.post` call performs its own, independent DNS resolution, and nothing
  pins that second resolution to the address(es) just validated.
- **Residual risk, accepted for v1: DNS-rebinding TOCTOU.** An attacker whose DNS
  answer changes between the pre-check's resolution and `requests`' own resolution
  a moment later (serving a public IP to the first, a private/internal IP to the
  second) slips through this gap. The module's own docstring names this as a known,
  accepted risk. **Fast-follow, not shipped:** IP-pinning the validated address into
  the actual connection, so the two resolutions can never disagree.
- **Scheme: https-only**, in this feature's actual usage. `send_webhook` exposes a
  generic `allow_http` escape hatch (for explicitly configured dev environments
  elsewhere), but the Agent-KV caller (`_maybe_webhook`) never passes it — every
  Agent-KV webhook is https-only in practice.
- **No redirects** (`allow_redirects=False`).
- **Fixed, minimal payload** (`{job_id, status}` only — see above) and the
  **response body is never read** — only the status code is inspected.
- **Short timeout** (10 seconds).
- **No retries.** One POST attempt only; any failure (host refused by the
  pre-check, timeout, connection error, non-2xx status) is logged and swallowed —
  there is no retry loop anywhere in this delivery path.

Test/dev stacks only: `AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1` on the
ide-callback worker waives both guards (http scheme and non-public host) so the
e2e lane can deliver to a receiver on the compose host. Never set it in
production.

## 10. Retention and TTL

- **Input deletion is completion-triggered, not TTL-based** (spec D10: "uploaded
  document deleted on job completion"). `FinalizeView.post`
  (`backend/agent_kv/internal_views.py`) deletes the staged input file and blanks
  `input_ref` the instant a finalize call actually wins the terminal-state guard (the
  job just became `COMPLETED` or `FAILED`), via `storage.delete_input` — which only
  ever touches `input_ref`, never `result_ref`/the result file. A duplicate/late
  finalize call (guard already lost, since the job is already terminal) never deletes
  anything: either the winning call already did, or the job reached terminal some
  other way (see next bullet).
- **Cancelled jobs' inputs intentionally ride TTL instead.** `JobCancelView` marks a
  job `CANCELLED` directly via `AgentKVJob.mark_terminal`, not through `FinalizeView`
  — so cancellation never triggers the completion-time delete above. A late finalize
  call against an already-`CANCELLED` job also no-ops (it loses the terminal guard,
  same as any duplicate). A cancelled job's staged input is therefore cleaned up the
  ordinary way: by the TTL sweep once `expires_at` passes, or by an explicit
  `DELETE /agent-kv/{job_id}`.
- **Result retention**: `AGENT_KV_RESULT_TTL_DAYS` (default **7** days, D10's
  engineering default) — results are re-readable until then, then swept by the
  internal `ttl-cleanup` endpoint ([§12](#12-deploy-checklist)), which blanks
  `result_ref` (and `input_ref` too, covering the cancelled-job case above, or
  defensively for any input that somehow outlives completion). The job row itself is
  never deleted (audit trail persists past TTL, only the object-store payloads are
  dropped).
- **`expires_at` is stamped at submit time**, not at completion —
  `SubmitView.post` sets `expires_at = timezone.now() + timedelta(days=AGENT_KV_RESULT_TTL_DAYS)`
  before dispatch even runs. **This is a real divergence from spec D10's framing**
  ("results retained 7 days" implicitly from completion): for a job that runs close to
  its `timeout` ceiling, the effective post-completion retention window is slightly
  under the full 7 days. Documented here as shipped behavior, not silently
  reconciled — flagged for anyone tightening D10 later.

## 11. When the engine is unavailable (501 behavior)

The Django backend cannot see the executor plugin registry (that lives in the workers
process). Dispatching to a queue no worker consumes would hang, not error — so gating
happens **before enqueue, in the backend**, via a capability probe:

```python
if not get_plugin("agent_kv"):
    raise EngineUnavailable()   # 501, "agent-kv engine not available on this deployment"
```

`get_plugin(...)` (`backend/plugins/__init__.py`) returns an empty dict — falsy — when
no `plugins/agent_kv/` package is installed, which is the OSS-only case by design (the
plugin is a cloud deliverable, spec §5.1/§11: "OSS scaffold merges dark"). Every
`POST /agent-kv/` on an OSS-only deployment therefore returns:

```json
{"detail": "agent-kv engine not available on this deployment"}
```

with HTTP `501`. `/validate`, key management, status/result/cancel/delete on
*already-existing* jobs are unaffected by this gate — only `SubmitView` probes it,
since only submit needs the engine.

### 11a. The cancel-at-pickup contract (internal API — frozen; build the cloud engine against this)

Spec §7.4 states that "a job not yet picked up is dropped at pickup," but leaves the
actual mechanism unspecified. This is it, and it is load-bearing enough that it is
recorded here explicitly rather than left to be inferred from the internal-API code:

`POST /internal/v1/agent-kv/jobs/{job_id}/stage/` — the stage-report endpoint
(`StageReportView`, `backend/agent_kv/internal_views.py`) — no-ops with
`{"ok": true, "noop": true}` whenever the target job is already terminal (its
candidate query excludes `AgentKVJob.TERMINAL`, so a terminal job's row is simply
never found). **That response body *is* the drop signal.** The FIRST stage report an
executor makes for a job it has just picked up doubles as a liveness check against a
job that was cancelled (or otherwise reached a terminal state) in the window between
dispatch and pickup — since there is no task-revocation machinery anywhere in the
platform (spec §7.4) to stop a picked-up job any other way.

On `noop: true`, the executor **must**:

1. Stop doing any further work on that job immediately.
2. **Still call `FinalizeView`** (`POST .../jobs/{job_id}/finalize/`) with whatever
   outcome it has — success or failure, it does not matter which, since the write is
   going to no-op either way.

Step 2 is not optional. `FinalizeView`'s terminal-state guard (spec §5.4) correctly
no-ops the status write for an already-terminal job — but its concurrency-slot
release (`AgentKVConcurrencyLimiter.release`) lives in a `finally`, unconditional on
whether the guard actually won ([§10](#10-retention-and-ttl) covers the input-deletion
side of this same guard). An executor that treats `noop: true` as "nothing left to do
here" and skips the finalize call entirely leaks that job's concurrency slot for the
rest of the limiter's TTL (6 hours) instead of releasing it immediately. This is the
entire mechanism behind a pre-pickup cancel actually being observed and cleaned up
promptly — there is no other signal.

## 12. Deploy checklist

Everything below is required (or worth checking) to run this feature for real,
beyond `docker compose up`:

1. **Cloud plugin**: install/enable the `agent_kv` backend capability plugin
   (probed via `plugins.get_plugin("agent_kv")`) — without it, submit always 501s
   ([§11](#11-when-the-engine-is-unavailable-501-behavior)). This repo ships gated
   dark by design; nothing to do for an OSS-only deployment except accept the 501.
   The marker the probe keys off is the mere presence of
   `backend/plugins/agent_kv/__init__.py` — a cloud image ships it (via the
   plugin-copy step), an OSS-only build does not.
2. **Executor worker fleet queue**: the executor dispatch derives its Celery queue name
   from the executor name as `celery_executor_{executor_name}` — for Agent-KV that's
   **`celery_executor_agentic_kv`** (`unstract/sdk1/src/unstract/sdk1/execution/dispatcher.py`).
   `workers/run-worker.sh`'s executor role default queue list
   (`celery_executor_legacy,celery_executor_agentic,celery_executor_agentic_table`)
   does **not** include it — a self-hosted/OSS-only deployment running the cloud
   `agentic_kv` executor plugin must add `celery_executor_agentic_kv` to that worker's
   consumed queues (`CELERY_QUEUES_EXECUTOR` on the Docker path, or the equivalent
   `run-worker.sh` queue map entry) or dispatched jobs will never be picked up.
   **The cloud Helm chart already wires this**: both `workerExecutorV2.args`
   (`--queues=...,celery_executor_agentic_kv`) and
   `workerPgExecutor.env.WORKER_PG_QUEUE_CONSUMER_QUEUE` include it, and both fleets
   carry `additionalConfigs: [..., agentKv]` (`charts/unstract-platform/values.yaml`,
   cloud repo) so the executor pods get the `AGENT_KV_*` LLM/LLMWhisperer env alongside
   the queue wiring.
3. **Callback queue**: the `ide_callback` worker must consume `agent_kv_callback`
   alongside its own `ide_callback` queue, or jobs dispatch but never finalize. This is
   already the hardcoded default in both `workers/run-worker-docker.sh` and
   `workers/run-worker.sh` (`WORKER_QUEUES["ide_callback"] = "ide_callback,agent_kv_callback"`)
   — nothing to configure for a standard deployment; see the note already in
   `docker/sample.env` under "IDE Callback Worker." The cloud Helm chart matches:
   `workerIdeCallbackV2.args` (`--queues=ide_callback,agent_kv_callback`) and
   `workerPgIdeCallback.env.WORKER_PG_QUEUE_CONSUMER_QUEUE`
   (`"ide_callback,agent_kv_callback"`) both already include it
   (`charts/unstract-platform/values.yaml`, cloud repo).
4. **Internal periodic maintenance — proxy tasks now exist; nothing schedules them
   yet.** Two internal endpoints do the real work
   (`backend/agent_kv/internal_urls.py`, `internal_views.py::SweepView`/
   `TTLCleanupView`), and thin scheduler-side proxy tasks now call them —
   `workers/scheduler/agent_kv_tasks.py::agent_kv_sweep`/`agent_kv_ttl_cleanup`,
   registered under the wire names `agent_kv.sweep`/`agent_kv.ttl_cleanup` — mirroring
   the dashboard-metrics periodics (`workers/scheduler/dashboard_metrics_tasks.py`)
   this feature was designed to follow (spec §5.4), except the call goes through the
   shared `InternalAPIClient` facade (`agent_kv_sweep`/`agent_kv_ttl_cleanup` methods on
   `workers/shared/api/internal_client.py`) rather than a second bespoke HTTP client.
   **Nothing calls these tasks on a schedule yet** — an operator must register both as
   periodic tasks via the same PG-scheduler mechanism the dashboard-metrics periodics
   use: a `PgPeriodicTask` row per task (`name`, `task_name` = the wire name above,
   `queue`, `cron_string`, `enabled=True`, `pg_owned=True` once ready to go live — see
   `backend/dashboard_metrics/migrations/0004_pg_periodic_tasks.py` for the exact row
   shape this mirrors) before relying on TTL cleanup or stuck-job recovery:
   - `agent_kv.sweep` → `POST /internal/v1/agent-kv/sweep/` — terminalizes `PENDING`
     jobs never dispatched within `AGENT_KV_SWEEP_GRACE_SECONDS` (default 1 hour)
     **and** `DISPATCHED`/`RUNNING` jobs stuck past `AGENT_KV_STUCK_JOB_GRACE_SECONDS`
     (default 6 hours) — two independent phases per call, response
     `{"swept": N, "timed_out": M}`. Suggested cadence: every few minutes.
   - `agent_kv.ttl_cleanup` → `POST /internal/v1/agent-kv/ttl-cleanup/` — deletes
     staged input/result files past `expires_at`. Suggested cadence: hourly or daily
     (retention is measured in days).
   Both endpoints are idempotent, batch-capped at 500 rows per phase per call, and
   safe to call more often than needed.

   **Cloud mechanism — Kubernetes CronJobs, not the PG-scheduler.** The sweep and
   TTL-cleanup logic itself lives in `backend/agent_kv/maintenance.py::run_sweep`/
   `run_ttl_cleanup` — `SweepView`/`TTLCleanupView` above are now thin wrappers
   around it. Two Django management commands wrap the same functions —
   `python manage.py agent_kv_sweep` and `python manage.py agent_kv_ttl_cleanup`
   (`backend/agent_kv/management/commands/`) — each printing the JSON counts
   (`{"swept": N, "timed_out": M}` / `{"cleaned": N}`) and exiting 0. In the cloud
   deployment, a Kubernetes CronJob runs each command on the cadences above instead
   of registering a `PgPeriodicTask` row. The scheduler proxy tasks
   (`agent_kv.sweep`/`agent_kv.ttl_cleanup`) and their PG-scheduler registration
   remain the mechanism for OSS/self-hosted deployments, which have no CronJob
   equivalent to drive from.

   **Chart keys (cloud repo)**: `backend.agentKvCronJobs` in
   `charts/unstract-platform/values.yaml` — `enabled: false` there (on-prem never runs
   it), flipped to `enabled: true` in `charts/cloud-deployment-values/cloud.values.yaml`.
   Its `jobs` list is the two commands above with concrete schedules:
   `{name: sweep, command: agent_kv_sweep, schedule: "*/15 * * * *"}` and
   `{name: ttl-cleanup, command: agent_kv_ttl_cleanup, schedule: "17 * * * *"}` — offset
   from sweep's :00/:15/:30/:45 ticks so the two CronJobs never contend on the same
   rows. Neither job needs the `agentKv` shared-config group (LLM/LLMWhisperer
   creds — only the executor touches those): sweep only needs `database`/`redis`,
   ttl-cleanup additionally needs `storage` for `AGENT_KV_FILE_STORAGE_CREDENTIALS`
   (see item 6 below) — both already on the `backend` deployment's config list.
5. **Env vars**: every `AGENT_KV_*` setting plus `AGENT_KV_FILE_STORAGE_CREDENTIALS` —
   see [§13](#13-environment-reference) and `docker/sample.env`. The executor-side vars
   (read by the cloud `agentic_kv` plugin, not by the backend settings in §13) are a
   separate chart group: `global.sharedConfigs.agentKv`
   (`charts/unstract-platform/values.yaml`, cloud repo) —
   `AGENT_KV_LLM_PROVIDER`, `AGENT_KV_LITE_MODEL`, `AGENT_KV_ADVANCED_MODEL`,
   `AGENT_KV_LLM_API_KEY`, `AGENT_KV_LLMWHISPERER_API_KEY`,
   `AGENT_KV_LLMWHISPERER_BASE_URL`, `AGENT_KV_MAX_TOKENS`, `AGENT_KV_PARALLEL_PAGES`,
   `AGENT_KV_ENGINE_VERSION`. Of those, two are ESO (External Secrets Operator)
   secrets rather than plain values — `AGENT_KV_LLM_API_KEY` and
   `AGENT_KV_LLMWHISPERER_API_KEY`, mapped in `global.externalSecrets.groups.agentKv`
   to the GCP Secret Manager suffixes `agent-kv-llm-api-key` /
   `agent-kv-llmwhisperer-api-key`. `AGENT_KV_LLM_PROVIDER` is a v1 hard allowlist of
   two values — `anthropic` and `openai` (`SUPPORTED_PROVIDERS` in the executor's LLM
   adapter) — anything else raises `ConfigError` at dispatch, before any LLM call.

   **Rollout order is strict, and getting it wrong takes down the whole executor
   fleet.** Both executor fleets mount this group with `envFrom: secretRef:
   <release>-agent-kv`, so no executor pod of any kind — not just Agent-KV ones —
   can start until that Secret exists: enabling the group ahead of its contents
   leaves `workerExecutorV2` and `workerPgExecutor` in `CreateContainerConfigError`.
   Per environment, in this order: (1) create the two GCP Secret Manager secrets
   `<externalSecrets.prefix>-agent-kv-llm-api-key` and
   `<externalSecrets.prefix>-agent-kv-llmwhisperer-api-key`; (2) set the three
   non-secret keys — `AGENT_KV_LLM_PROVIDER`, `AGENT_KV_LITE_MODEL`,
   `AGENT_KV_ADVANCED_MODEL` — in that environment's own values file (under ESO they
   are emitted as inline literals in the ExternalSecret's `target.template`, and a nil
   value is silently **dropped**, so leaving them unset ships a Secret without them and
   every Agent-KV job then fails at dispatch with `ConfigError: Missing required
   Agent-KV env vars`); (3) only then roll the fleets out. `cloud.values.yaml` enables
   the group fleet-wide, so step 2 is a per-environment prerequisite, not an optional
   extra. In inline (non-ESO) mode the same three keys are enforced at render time by a
   `fail` guard in `charts/unstract-platform/templates/shared/agent-kv-secret.yaml`, so
   a mistake there is a loud deploy-time failure instead of a per-job runtime one.
6. **Object storage**: `AGENT_KV_FILE_STORAGE_CREDENTIALS` must point at a real bucket
   in production (defaults to the same shared MinIO instance as workflow execution).
   Paths are prefix- and org-rooted
   (`{AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/{job_id}/input{ext}`, `.../result.json`) —
   no document bytes ever ride the message broker. Chart key:
   `global.sharedConfigs.storage.AGENT_KV_FILE_STORAGE_CREDENTIALS`
   (`charts/unstract-platform/values.yaml`, cloud repo) — derived from
   `fileStorageCredentials`/`MINIO_CREDS` unless set explicitly, the same fan-out
   pattern as its three siblings (`WORKFLOW_EXECUTION_`, `API_`,
   `HITL_FILES_FILE_STORAGE_CREDENTIALS`).
7. **`AGENT_KV_STORAGE_DIR_PREFIX` — must be set on the backend *and* the executor
   fleet, to the same value** (default `unstract/agent_kv`). The **first segment is the
   bucket** — s3fs/gcsfs read it that way — so it must be a bucket that already exists
   (the MinIO dev bootstrap creates `unstract`); a bucket-less prefix makes every submit
   fail `NoSuchBucket` and return a 500 with nothing billed. The executor reads the
   backend-staged `input_ref` and keys its OCR cache under the same root
   (`{prefix}/{org_id}/cache/…`), so a mismatch silently splits the cache and breaks
   result read-back. Unlike the executor-only group in item 5, this one has to reach
   **both** sides, so in the chart (cloud repo) it must be fanned out to the backend
   *and* to `workerExecutorV2`/`workerPgExecutor` from a single source of truth — never
   set independently per fleet, where the two can drift apart unnoticed.
8. **Feature flags — `calculations` and `structured_output`**: the cloud engine
   cannot execute these yet, so submit rejects them with a 400 until the flags are
   flipped. Both `AGENT_KV_CALCULATIONS_ENABLED` and
   `AGENT_KV_STRUCTURED_OUTPUT_ENABLED` default `false`; set either to `true` only
   once the executor side has shipped support for it.
9. **Executor time limit — the real baseline is 3,600s, not 7,200s.** The executor
   fleet (`workerExecutorV2`/`workerPgExecutor`) is not a `FILE_PROCESSING` worker —
   `WorkerConfig._get_worker_specific_timeout_defaults()`
   (`workers/shared/models/worker_models.py`) falls through to the "conservative
   defaults for other workers" branch for `WorkerType.EXECUTOR`: **1 hour / 3,600s**
   hard limit, 3,300s soft. The chart's bare `TASK_TIME_LIMIT: "3600"` ConfigMap key
   is inert — `get_celery_setting`'s 4-tier resolution (cmdline →
   `{WORKER_TYPE}_{SETTING}` → `CELERY_{SETTING}` → default) means only
   **`EXECUTOR_TASK_TIME_LIMIT`** (worker-specific) or `CELERY_TASK_TIME_LIMIT`
   (global) actually override it; see the comment on `workerExecutorV2`'s
   `terminationGracePeriodSeconds` in `charts/unstract-platform/values.yaml`, which
   already documents this ("Its ceiling is task_time_limit=3600s... note the chart's
   bare TASK_TIME_LIMIT is NOT read; only EXECUTOR_TASK_TIME_LIMIT / CELERY_*").
   At the 100-page cap (`AGENT_KV_MAX_PAGES`) with `extraction_mode="per-page"`,
   `parallel_pages=4`, and both QA and challenge enabled (the worst-case option
   combination), the arithmetic worked out in Task 9's report is: each of
   `key_extractor` → `kv_qa` → `kv_challenger` fans 100 pages across 4 workers (25
   sequential rounds), each round up to ~99s if its slowest call needs a *full* retry
   backoff (`SDKLLMClient`'s `_DEFAULT_MAX_RETRIES=8`) — 25 × 99s = 2,475s per stage,
   3 stages sequential = **7,425s**, a gap of **3,825s (over 2x)** against the real
   3,600s baseline, not the 225s a 7,200s baseline would suggest. That 7,425s figure
   assumes every single call across all 300 (100 pages × 3 stages) hits the full
   8-retry backoff, which is not realistic — a real call is ~10-30s, so a full run at
   the page cap is closer to **~2,000-2,500s** in practice; the 7,425s number is a
   theoretical ceiling for capacity planning, not an expected duration.
   **Recommendation: do not raise the fleet-wide time limit preemptively.**
   `EXECUTOR_TASK_TIME_LIMIT` is fleet-wide — every executor task (every plugin, not
   just Agent-KV) inherits it, and it's coupled to `workerPgExecutor`'s PG-visibility
   lease/`vt` and `terminationGracePeriodSeconds` (raising one without the others
   reintroduces the mid-flight-SIGKILL/silent-redelivery risk `UN-3964`'s comment on
   `workerExecutorV2` already guards against). Measure real per-page timings from the
   Task 13 integration run first, then either raise `EXECUTOR_TASK_TIME_LIMIT` (and
   `terminationGracePeriodSeconds`/the PG lease together, not alone) or lower
   `AGENT_KV_MAX_PAGES` for deployments that see per-page-heavy, near-cap documents in
   practice.

   **What actually happens at each limit.** At the **soft** limit (3,300s) Celery raises
   `SoftTimeLimitExceeded` into the task; the executor catches it, sets a run-level stop
   signal that makes every in-flight LLM retry loop abort at its next backoff instead of
   sleeping through the remaining ladder (up to ~30s per attempt × 8 attempts), flushes
   the usage records accrued so far, and finalizes the job `failed` with the user-safe
   error `"timed out"`. At the **hard** limit (3,600s) the worker is SIGKILLed: usage
   records still held in memory are lost, so that run's LLM spend goes **unmetered**
   (page usage, posted per-OCR-call, is unaffected). That gap is the reason the soft
   limit now stops retries promptly — it is what keeps a slow run from crossing into the
   hard kill.
10. **Testing lanes — Docker-free unit gate, Docker-required integration lane.** The
    cloud rig's `unit-agentic-kv` group (`tests/groups.cloud.yaml`, cloud repo) runs the
    executor plugin's own test suite in an isolated venv with no `requires_services` —
    no Docker needed, and it's what `tox -e unit` (CI's unit-tier matrix leg) runs. The
    integration tier is the one that needs Docker: it authenticates to the container
    registry and boots a mock Auth0 sidecar (`.github/workflows/ci-test.yaml`, cloud
    repo) for the cross-service suites. A local `unit-agentic-kv` run needs neither
    Docker nor the platform stack up.

    **A real-key Agent-KV e2e run cannot go through `tests.rig run`.** Whenever a
    selected group needs the platform, the rig sets `UNSTRACT_LLM_MOCK_RESPONSE`
    to `MOCK_LLM_OK` (`tests/rig/cli.py`) — and an exported *empty* value counts as
    unset, so there is no way to opt out from inside the rig; the lane then exercises
    the mock, not a provider. To run it against real LLMWhisperer/LLM keys, boot the
    stack first (`python -m tests.rig platform up`, or `docker compose` with
    `tests/compose/docker-compose.test.yaml`) and then invoke pytest directly with
    `UNSTRACT_BACKEND_URL`, `AGENT_KV_E2E=1` and the `AGENT_KV_*` keys exported:
    `AGENT_KV_E2E=1 UNSTRACT_BACKEND_URL=http://localhost:8000 pytest tests/e2e/agent_kv`.

    Two scenarios are operator-gated on top of that: the bad-LLM-key scenario
    (`AGENT_KV_E2E_BAD_KEY_JOB=1`, see the test module docstring) and the
    completion-webhook scenario, which needs
    `AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1` set BOTH on the
    ide-callback worker (it waives the webhook SSRF guards — https scheme +
    public host — for test/dev stacks only; never set it in production) and in
    the pytest process env; the receiver is reached via
    `host.docker.internal` (the compose host-gateway mapping). The lane also
    covers sync-wait submits (`timeout` → 200 with the inline result) and an
    `.xlsx` document (`fixtures/invoice.xlsx`, the no-pre-OCR-page-count path).
11. **Sandbox worker — calculations codegen fleet** (when
    `AGENT_KV_CALCULATIONS_ENABLED=true`). The optional `calculations` field
    invokes out-of-process codegen and execution in a dedicated sandbox worker fleet
    consuming the `sandbox_codegen` Celery queue. **Deployment order is strict:**
    deploy the sandbox worker (Deployment healthy, actively consuming tasks from
    `sandbox_codegen`) **before** flipping `AGENT_KV_CALCULATIONS_ENABLED=true`.
    With the flag on but the sandbox down, calculation jobs fail user-safely at the
    RPC timeout (they do not hang past it); however, **never leave the flag on
    without a healthy sandbox fleet**, as all jobs with `calculations` will eventually
    exceed their timeouts and return failures to callers.

    **Security posture:** The sandbox pod carries no LLM, OCR, or storage secrets and
    runs with default-deny egress — it only executes generated calculation code against
    the extracted record in-memory. User-supplied `calculations` expressions are
    validated through an AST gate (layer 1 of a 5-layer defense-in-depth model) at
    submit time before ever reaching the sandbox, and further constrained (parsing,
    type-checking, capability allowlist) at execution time. This layered defense prevents
    unbounded code execution and resource exhaustion from untrusted input.

    **Accepted v1 residual (arbitrary in-pod file reads):** because generated code
    legitimately needs `open()`/`pathlib` for its input and output files, untrusted
    calculation code can read world-readable files inside its own sandbox pod and
    return the contents to the submitter. This is contained — not by the AST gate, but
    by the pod's layers 2–5: no secrets in the pod (not even the platform
    `ENCRYPTION_KEY`), non-root on a read-only rootfs, default-deny egress (no
    exfiltration), per-job isolation, and results returned only to the submitting
    key — so the worst case is disclosure of a non-sensitive container file to the
    customer who submitted the job. The deferred hardening for this is a
    `runtimeClass: gvisor` sandbox. Consequently the sandbox pod's default-deny egress
    and no-secrets posture are load-bearing and must not be relaxed.

## 13. Environment reference

All `AGENT_KV_*` settings (`backend/backend/settings/base.py`), each `os.environ.get`
with the default shown:

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_KV_PATH_PREFIX` | `agent-kv` | Top-level public URL prefix (whitelisted past tenant middleware). |
| `AGENT_KV_MAX_FILE_SIZE_MB` | `50` | Submit-time file size cap. |
| `AGENT_KV_MAX_PAGES` | `100` | Pre-OCR page cap for PDFs/images (§6.1). |
| `AGENT_KV_MAX_CALCULATIONS_BYTES` | `20000` | Byte cap on the optional `calculations` field. |
| `AGENT_KV_MAX_SCHEMA_BYTES` | `262144` | Byte cap on the raw `keys` JSON document (256 KiB). |
| `AGENT_KV_RESULT_TTL_DAYS` | `7` | Result retention window (and a cancelled job's input, which rides the same TTL — a completed/failed job's input is deleted immediately at finalize instead), stamped at submit time (see [§10](#10-retention-and-ttl)). |
| `AGENT_KV_MAX_TIMEOUT_SECONDS` | `300` | Upper bound on the submit `timeout` (synchronous-wait) field. |
| `AGENT_KV_CONCURRENT_LIMIT` | `5` | Per-organization concurrent in-flight job cap (own Redis namespace, fails open on Redis errors). |
| `AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE` | `60` | Per-key request rate limit (submit + validate), fails open on Redis errors. |
| `AGENT_KV_SWEEP_GRACE_SECONDS` | `3600` | Age (from `created_at`) before a never-dispatched `PENDING` job is eligible for the sweep. |
| `AGENT_KV_STUCK_JOB_GRACE_SECONDS` | `21600` | Age (from `dispatched_at`) before a `DISPATCHED`/`RUNNING` job is eligible for the sweep's stuck-job phase — force-failed as `"Job timed out"` (6 hours). |
| `AGENT_KV_CALCULATIONS_ENABLED` | `false` | Gates the submit `calculations` field; the engine cannot execute it yet, so submit 400s while this is off. |
| `AGENT_KV_STRUCTURED_OUTPUT_ENABLED` | `false` | Gates the submit `structured_output` field; the engine cannot execute it yet, so submit 400s while this is off. |
| `AGENT_KV_STORAGE_DIR_PREFIX` | `unstract/agent_kv` | Bucket-rooted object-store root for staged inputs/results (`{prefix}/{org_id}/{job_id}/…`), mirroring `WORKFLOW_EXECUTION_DIR_PREFIX`/`API_EXECUTION_DIR_PREFIX`. The **first segment is the bucket** and must already exist. The cloud executor reads the same variable and keys its OCR cache under `{prefix}/{org_id}/cache/…`, so both fleets must agree. Trailing `/` is stripped. |
| `AGENT_KV_FILE_STORAGE_CREDENTIALS` | *(none — must be set)* | JSON credentials for the `AGENT_KV` `FileStorageType` (`unstract/filesystem`), same shape as `WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS`: `{"provider": "minio", "credentials": {"endpoint_url": "...", "key": "...", "secret": "..."}}`. |

`AGENT_KV_FILE_STORAGE_CREDENTIALS` is looked up via
`FILE_STORAGE_CREDENTIALS_TO_ENV_NAME_MAPPING[FileStorageType.AGENT_KV]`
(`unstract/filesystem/src/unstract/filesystem/file_storage_config.py`) and is required
for `stage_input`/`write_result`/`read_result`/`delete_job_files`/`delete_input`
(`backend/agent_kv/storage.py`) to have anywhere to write to.
