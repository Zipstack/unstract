# Agent-KV API

Agent-KV is Unstract's agentic key-value extraction product: upload a document plus a
`keys.json`-style extraction schema, get back a job id, poll a verbose agent-centric
status document, and fetch a rich result (record + per-field QA/challenger audit
trail).

This document describes the API **as built in this repo** — the OSS scaffold (routes,
validation, dispatch, job lifecycle, key management). The document, `keys.json` schema,
and OCR/LLM extraction pipeline itself are described only insofar as they shape the
contract; the extraction engine ships as a cloud executor plugin (see
[§6, 501 behavior](#10-when-the-engine-is-unavailable-501-behavior) below).

Design background: `docs/superpowers/specs/2026-08-28-agent-kv-api-design.md` (referred
to as "the spec" throughout this document; section numbers below are spec section
numbers). This document records what shipped, including a handful of places where the
implementation is more specific than — or diverges from — the spec's sketch. Those are
called out explicitly rather than silently reconciled.

## 1. Authentication

There are two independent auth schemes on two different URL prefixes:

| Surface | Prefix | Auth |
|---|---|---|
| Public execution API (submit/status/result/cancel) | `/api/v1/agent-kv/…` (under the platform API prefix, beside the tenant subfolder rather than inside it) | `Authorization: Bearer <AgentKVKey>` — a dedicated per-organization key, validated by the view itself |
| Key management (create/list/rotate/revoke) | `{PATH_PREFIX}/unstract/…/agent-kv/keys/…` (tenant-scoped, alongside Platform API key management) | Session auth, `IsOrganizationAdmin` only |

The execution prefix (`AGENT_KV_PATH_PREFIX`, default `api/v1/agent-kv`) sits **outside** the
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
`IsOrganizationAdmin` (`backend/agent_kv/permissions.py`). It is shaped on
`platform_api.views.PlatformApiKeyViewSet`, including **where the plaintext key is
and is not returned**:

| action | serializer | `key` |
|---|---|---|
| `list` | `AgentKVKeyListSerializer` | masked, `****-<last 4>`; adds `created_by_email` |
| `retrieve` / `create` / `rotate` | `AgentKVKeyDetailSerializer` | **full value** |
| `create` (request) | `AgentKVKeyCreateSerializer` | `name`, `description`, both required and sanitised |
| `partial_update` (request) | `AgentKVKeyUpdateSerializer` | `description`, `is_active` |

The split exists because `list` backs a table of every key in the organization:
returning real values there puts the whole set on screen to read one of them. The
three single-key responses each answer a deliberate request for one key.

**Getting the adapter ids**: each adapter row under *Settings → LLMs /
X2Text* has a **Copy ID** button in its action column
(`ResourceTable`'s opt-in `handleCopyId`, wired by
`frontend/src/components/tool-settings/tool-settings/ToolSettings.jsx`). That
copies the instance UUID this API expects — not `adapter_id`, which is the
provider descriptor (`anthropic|90ebd4cd-…`) shared by every instance of that
provider and rejected here as "no such adapter in this organization". The same
ids are listable at
`GET {PATH_PREFIX}/unstract/{org}/adapter/?adapter_type=LLM`.

**Browser UI**: *Settings → Agent-KV API Keys*
(`frontend/src/components/settings/agent-kv-keys/AgentKvKeys.jsx`, routed at
`settings/agent-kv-keys` behind `RequireAdmin`). It is a thin wrapper over the shared
`ApiKeyManager` screen that also backs Platform API keys and Global API deployment
keys — create, copy, rotate, enable/disable and delete. Admin-only, matching
`IsOrganizationAdmin` on the viewset.

Routes (`backend/agent_kv/urls.py`, mounted at `agent-kv/` under
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

> **This section describes the `kv` extractor's schema language, which is not
> routable on this deployment** (see [§3](#3-submit--post-agent-kv-multipart)).
> It is documented here because the compiler ships and the language is frozen,
> so an integration can be written against it ahead of the extractor's release.
> The `table` extractor's `keys` is just `{"target_table": "<name>"}` and needs
> none of this.

The `keys` submit field — spec-called "keys.json" — is a JSON object describing what to
extract. It compiles through `unstract.agent_kv_schema.compile_schema`
(`unstract/agent-kv-schema/src/unstract/agent_kv_schema/`), the **single schema compiler
in the system**: the OSS API validates with it at submit time, and
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

  `_dedup` (optional, default `true`) controls whether rows identical in **every**
  extracted column are collapsed to one. Leave it on for documents where
  layout-preserving OCR repeats a row once per replicate column — that is what it
  exists for. Set it to `false` when your documents can genuinely contain two
  identical rows:

  ```json
  "line_items": {
    "_dedup": false,
    "_array": {
      "description": {"description": "Line description"},
      "total": {"description": "Line total", "format": "currency"}
    }
  }
  ```

  With `_dedup: true` an invoice listing the same item twice comes back with one
  row, so the row count — and any `_constraints` aggregate over those rows — is
  wrong. The default is `true` only because flipping it would break the OCR corpus
  the extractor was built against; it is not the safer value for every document.
  Must be a JSON boolean: `"false"` as a string is rejected rather than silently
  read as true.

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
(`AGENT_KV_MAX_CALCULATIONS_BYTES`) — see [§13 env reference](#12-environment-reference).

A schema that fails to compile is rejected with a `400` at submit time — **nothing is
billed**.

## 3. Submit — `POST /api/v1/agent-kv/` (multipart)

Copied verbatim from spec §7.1 and cross-checked field-by-field against
`backend/agent_kv/execution_serializers.py::SubmitSerializer` — every row below matches
the shipped serializer exactly; no drift found in the submit contract itself (see the
notes after the table for two spec-vs-code nuances worth flagging).

The request is **extractor-scoped**: a per-extractor schema and its knobs live inside
`extractors`, and only fields describing the request itself stay top level.

**Job-level fields:**

| Field | Required | Notes |
|---|---|---|
| `file` | yes | One document per job (D12). |
| `extractors` | yes | JSON array (file part or inline JSON string), one entry per extractor. Compiled synchronously; invalid ⇒ 400, nothing billed. |
| `page_start`, `page_end` | no | 1-based inclusive range. **Job-level, not per-extractor**: the range drives the shared OCR pass and the page cap, so it cannot differ between extractors reading the same document. |
| `timeout` | no | Omitted or `0` = pure async (immediate 202). `1–300`: the view polls the job row up to the deadline and returns the result inline if the job completes, else 202 with the job id. |
| `tags`, `custom_data` | no | Echoed through. |
| `webhook_url` | no | Terminal-state POST `{job_id, status}` only — no result payload. **https, public host**; anything the delivery guard would refuse is a 400 at submit (§8). |

**Each `extractors` entry:**

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Which extractor. **`table` is the only supported value on this deployment**; anything else, `kv` included, ⇒ 400 (see the note below). More than one entry ⇒ 400 — the format is in place for multi-extractor jobs, the execution is not built yet. |
| `keys` | yes | This extractor's own request. For `table`, `{"target_table": "<the table to extract>"}` — the engine's one required extraction parameter. |
| `adapters` | yes (for `table`) | The platform adapter instances this extraction runs on: `{"llm": "<uuid>", "lite_llm": "<uuid>", "x2text": "<uuid>"}`. All three required. See **§3a** below. |
| `options` | no | This extractor's own knobs (below). An unrecognised option ⇒ 400, so a knob aimed at the wrong extractor fails loudly instead of being silently dropped. |

### 3a. `adapters` — you supply the models and the OCR credentials

The `table` extractor runs on **your own platform adapters**, named by id. Create
them once in Unstract (Settings → Adapters, or the adapter API) and pass their ids
on every submit:

| Role | Adapter type | What it does |
|---|---|---|
| `llm` | `LLM` | Structure detection and extraction — the quality-critical model. |
| `lite_llm` | `LLM` | Per-page table-presence detection. Runs once per page, so this is the cost-critical one; a cheap fast model belongs here. |
| `x2text` | `X2TEXT` | OCR. An LLMWhisperer adapter, which also carries the endpoint — there is no separate base-URL field. |

Each id is validated at submit, against **your organization** and against the
expected adapter type. A ⇒ 400, before anything is staged or billed:

- an id that is not your organization's — reported identically to one that does not
  exist, deliberately, so the endpoint cannot be used to discover which adapter ids
  are real elsewhere
- an id of the wrong type, e.g. an `X2TEXT` adapter in the `llm` slot
- a missing role, or an unknown one

Page usage and token usage are metered against the adapters you named, so **model
choice and LLM spend sit on your account**, per job.

> **This is a deliberate reversal of the original design (spec D6).** D6 specified
> that this API would have "no platform adapters by design", with models and OCR
> credentials configured by the operator in environment variables and "no end-user
> model control". That was the right call while the API's consumer was hypothetical;
> it is the wrong one now that the consumers are existing Unstract customers. They
> already own adapters, there was no operator-level LLM credential anywhere in the
> platform to reuse — LLM credentials live in per-organization adapter rows,
> encrypted — and env configuration would have put every customer's model choice and
> every customer's LLM spend on a single shared operator key.
>
> Consequences worth knowing: the API is no longer usable by a caller who has never
> signed in, since adapters must exist first; and the six `AGENT_KV_LLM_*` /
> `AGENT_KV_LLMWHISPERER_*` environment variables are **not read on the table path**
> (they remain in place for the `kv` extractor, which is still env-configured).
>
> One thing this does not honour: adapters carry per-user visibility within an
> organization, and an Agent-KV key resolves to an organization rather than a user.
> So a key may use **any** adapter in its own organization. A key is already an
> organization-level credential, so this is a deliberate decision rather than an
> oversight — but treat key issuance accordingly.

> **Why `kv` returns 400 here.** This deployment ships the table extractor only.
> The `kv` extractor's engine runs on its own release track and nothing on this
> deployment consumes its queue, so the API refuses a `kv` submit outright
> rather than accepting it with a `202` for a job that would never run. The
> wire format is unchanged: when `kv` ships, it becomes a second accepted value
> of `name` and nothing else about this document changes.

**`kv` options:**

| Option | Notes |
|---|---|
| `qa` | Default **on**. |
| `challenge` | Default **on** (~doubles LLM spend; meter records what ran). |
| `extraction_mode` | `whole-doc` (default) \| `per-page`. |
| `structured_output` | Disabled by default; enabled per deployment via `AGENT_KV_STRUCTURED_OUTPUT_ENABLED`. |
| `calculations` | Post-processing instructions; opt-in codegen. Disabled by default; enabled per deployment via `AGENT_KV_CALCULATIONS_ENABLED`. |
| `document_class` | Free-text hint (as CLI). |
| `key_notes` | Free-text notes appended to the prompt (as CLI). |

**`table` options:**

| Option | Notes |
|---|---|
| `instructions` | Free-text extraction guidance handed to the engine. |
| `json_structure` | Free-text description of the row structure to return. |
| `enable_header_mapping` | Default **off**. **Changes the result shape** — see [§5](#5-result--get-agent-kvjob_idresult). |
| `correct_number_separators` | Default **off**. Re-reads thousands/decimal separators in numeric cells. |
| `number_format` | `US` (default) \| `EU`. Which convention `correct_number_separators` assumes. |

Not exposed for `table` (they are meaningless on a blind API): `output_path`,
`enable_highlight`, and the IDE callback hints `prompt_key`/`doc_name`.

> **No backward compatibility with the pre-`extractors` flat shape.** `keys`, `qa`,
> `challenge`, `extraction_mode`, `structured_output`, `calculations`,
> `document_class` and `key_notes` are no longer accepted at top level — a request
> using the old form gets a 400 for the missing `extractors` field. The API had no
> consumers when this changed, so no alias was kept.

Not exposed (D6): model choice, challenger model, `parallel_pages`, thinking budgets.

**Two implementation-level notes not visible in the table:**

- File type is allowlisted (`.pdf .xlsx .xls`) and size-capped
  (`AGENT_KV_MAX_FILE_SIZE_MB`); PDFs are page-counted **locally, pre-OCR**, via
  `pdfplumber` and rejected over `AGENT_KV_MAX_PAGES` before any paid work runs. Excel
  has no pre-OCR page concept — it is capped by file size only at submit time (the
  engine enforces a post-OCR virtual-page cap).
  - **The cap is on the DOCUMENT, and a page range does not reduce it.** It is
    checked against `pages_total`, so pages 1–50 of a 400-page PDF is refused
    under a 100-page cap exactly as the whole document would be.

    This reads as unfriendly until you look at what a range actually costs. The
    engine renders every page and OCRs the whole file — `X2Text.process` is
    given the input path and no range — and `page_start`/`page_end` then choose
    which of the rendered pages the extraction agents read. So pages 1–5 of a
    400-page document costs 400 pages of OCR and is billed for 400. Capping the
    range would let a caller buy 400 pages of OCR under a 100-page limit.

    The worker refuses on the same quantity (cloud `api_binding.py`), which is
    the other half of the reason: a submit cap on anything else accepts
    requests the worker then fails — after the 202, after the concurrency slot
    and after the upload.

    `pages_selected` is computed internally but is **not** returned anywhere:
    the status document and the page-limit error both report `pages_total`. If
    OCR ever honours the range, this is the line to revisit — and the count
    the cap checks is what would change.
  - Images (`.png .jpg .jpeg .tiff`) are **not** accepted, and no longer count as
    1 page. The engine treats only `.pdf/.xlsx/.xls` as a document and
    `ImageLoader.load_pages` has no call site, so an accepted image returned
    `success: true` with every key not-found and a page billed. They are refused at
    submit until the engine side is wired.
- `timeout`'s upper bound is not the literal `300` in the spec prose — it's
  `AGENT_KV_MAX_TIMEOUT_SECONDS` (default `300`, but deployment-configurable).

### Response

`202` (async, the default):

```json
{
  "job_id": "5b6e9b0a-...",
  "status": "dispatched",
  "status_url": "/api/v1/agent-kv/5b6e9b0a-...",
  "created_at": "2026-08-28T10:15:00.123456+00:00"
}
```

`200` (when `timeout` was set and the job finished before the deadline): the full
[result payload](#5-result--get-agent-kvjob_idresult), same shape as the result
endpoint.

`501`: [engine unavailable](#10-when-the-engine-is-unavailable-501-behavior).
`429`: rate-limited (per-key request rate, or per-org concurrent-job limit — see
[§6](#12-environment-reference)).
`402`: the organization's subscription does not permit the request — its trial has
expired, or the subscription is inactive. Nothing is dispatched and nothing is
billed. This is the same gate, the same policy and the same response bodies an
API deployment execute gets from the cloud subscription middleware; Agent-KV
applies it in the submit view instead, because its URL carries no org segment for
that middleware to resolve an organization from. Cloud-only: an OSS-only
deployment returns `501` before ever reaching it.
`400`: serializer/schema validation failure — nothing billed.

### Example — `table` (the only extractor this deployment accepts)

```bash
curl -X POST https://api.unstract.example/api/v1/agent-kv/ \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345" \
  -F "file=@invoice.pdf" \
  -F 'extractors=[{
        "name": "table",
        "keys": {"target_table": "Line items"},
        "adapters": {
          "llm":      "7f3c1a90-0000-4000-8000-000000000001",
          "lite_llm": "7f3c1a90-0000-4000-8000-000000000002",
          "x2text":   "7f3c1a90-0000-4000-8000-000000000003"
        },
        "options": {
          "instructions": "Ignore the summary block at the foot of the page",
          "enable_header_mapping": true
        }
      }]' \
  -F "page_start=1" -F "page_end=5" \
  -F "webhook_url=https://example.com/hooks/agent-kv"
```

The three adapter ids are yours, from your own organization — see §3a. Omit any of
them and the submit is a 400.

### Example — `kv`

Shown for the wire format only; **`kv` returns 400 on this deployment** (see the
note above). Note it takes no `adapters` block: the `kv` extractor is
env-configured on the operator side.

```bash
curl -X POST https://api.unstract.example/api/v1/agent-kv/ \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345" \
  -F "file=@invoice.pdf" \
  -F 'extractors=[{
        "name": "kv",
        "keys": {
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
        },
        "options": {"challenge": false}
      }]' \
  -F "webhook_url=https://example.com/hooks/agent-kv"
```

## 4. Status — `GET /api/v1/agent-kv/{job_id}`

Verbose, agent-centric, stage-level (`backend/agent_kv/execution_views.py::_status_document`).
**Stage names are per-extractor.** They are wire format, and `qa`/`challenge`/`codegen`
mean nothing to the table extractor, so a job's recorded stages are filtered through the
list for the extractor that actually ran
(`backend/agent_kv/constants.py::STAGE_NAMES_BY_EXTRACTOR`).

- `kv` (superset; only stages that actually ran for this job appear, in a fixed
  order): `document_processing, extraction, qa, challenge, normalize, constraints,
  codegen, code_execution`.
- `table`: `table_extraction` — a single stage. The table engine exposes no node-level
  progress hooks, so finer stage names would describe progress the executor cannot
  actually report. It re-reports `table_extraction` as `running` while the engine works,
  carrying a `steps` counter that increases as the engine passes its own progress points.

```json
{
  "job_id": "5b6e9b0a-...",
  "status": "running",
  "extractors": {
    "kv": {
      "stage": "challenge",
      "stages": [
        {"name": "document_processing", "status": "done", "seconds": 6.2},
        {"name": "extraction", "status": "done", "seconds": 11.4},
        {"name": "qa", "status": "done", "seconds": 4.1},
        {"name": "challenge", "status": "running"}
      ]
    }
  },
  "adapters": {
    "llm": "3f2b1c90-...",
    "lite_llm": "a71e4d55-...",
    "x2text": "c90aa812-..."
  },
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

`adapters` echoes the platform adapter ids this job was dispatched with, by role
— the ones the submit named and the gate validated (§3a). It is reported because
the caller chose them and is paying for them: naming the wrong `llm` id yields a
correct-looking result at a different price, and the only other record of what
was spent is in `usage_v2`, which the caller cannot read. **Ids only, never
adapter metadata** — that is where provider credentials live. `{}` for an
env-configured extractor (`kv`) and for any job predating the field.

`status` is lowercased (`pending`, `dispatched`, `running`, `completed`, `failed`,
`cancelled`); `error` is included (only) when `status == "failed"`. `adapters`,
`pages_total` and `completed_at` are always present (as `null`/`{}` until known) — an addition beyond the
spec's illustrative example, not a drift, since spec §7.2 was explicitly a partial
sample ("Verbose, agent-centric, stage-level").

```bash
curl https://api.unstract.example/api/v1/agent-kv/5b6e9b0a-... \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 5. Result — `GET /api/v1/agent-kv/{job_id}/result`

Re-readable until `expires_at` (D11), plus explicit `DELETE`.

- **Non-terminal job** (`PENDING`/`DISPATCHED`/`RUNNING`): `409` with
  `{"status": "<lowercased status>"}`.
- **Expired, `COMPLETED` with an already-swept/blank `result_ref`, or purged by
  `DELETE`/TTL cleanup**: `404`. The purge case is keyed off the job's
  `files_purged` marker, not off a blank ref — `DELETE` deliberately keeps a ref
  whose object delete failed so TTL cleanup can retry it, so a surviving ref is
  not evidence that the data is still yours to read ([§7](#7-delete--delete-agent-kvjob_id)).
- **`COMPLETED`**: `200` with the engine's full result object, unchanged (record,
  normalized_record, per-field audit trail, `qa_passed`, `challenge_passed`,
  `consistency_violations`, `cost_summary`, `timing`, plus the advisory markers that
  qualify `qa_passed`/`challenge_passed` — spec §4; this repo does not shape or
  re-validate that payload, it stores and replays exactly what the executor's finalize
  call sent, so **this document is the only deprecation path for a change to it**).
- **`FAILED`**: `200` with
  `{"success": false, "status": "failed", "error": "<user-safe message>"}`.
- **`CANCELLED`**: `200` with `{"success": false, "status": "cancelled"}` — unless
  the cancel lost a race to an extraction that had already finished, in which case
  the result is served: `200` with `{"success": true, "status": "cancelled",
  "extractors": {...}, "usage_summary": {...}}`. The status stays `cancelled`
  because the cancel *was* honoured; `success` is `true` because there is a real
  result and it was already billed. Branch on `success` for "is there data",
  on `status` for "was this cancelled" — see
  [§6](#6-cancel--post-agent-kvjob_idcancel).

**Calculation result shape** (when `calculations` is supplied and
`AGENT_KV_CALCULATIONS_ENABLED=true`): a `COMPLETED` result adds these fields to the
engine's standard result object:

- `calculations_applied: bool` — **branch on this first.** `true` means codegen ran and
  the fields below are present; `false` means the per-job token ceiling skipped the
  `code_generator` stage, and then `execution` and `codegen_validation_passed` are
  **absent entirely** (see "Budget-skipped calculations" below). The key itself is
  absent on a job that requested no `calculations` at all, so read it with
  `result.get("calculations_applied")` rather than treating a missing key as `false`.
- `execution: {success: bool, rows_written: int, error: string|null}` — sandbox worker
  execution status. `success` is `true` if the generated code ran without error;
  `rows_written` is the count of rows the code emitted; `error` is `null` on success, or
  a user-safe message (e.g., `"Runtime error: division by zero"`) on failure.
  **Present only when `calculations_applied` is `true`.**
- `codegen_validation_passed: bool` — whether the generated code passed a **flake8
  lint** (`flake8 --ignore=E501,W503 --max-line-length=120`). **It is not the AST safety
  gate**, despite the name. This field is a code-*quality* signal with no security
  meaning. The AST gate is a separate, fail-closed, server-side control re-run inside
  the sandbox worker (the engine's client-side copy is never trusted), and a gate
  rejection is **never** visible here: it makes the whole job **fail**, so the result is
  the `FAILED` body above — which carries no `execution` block and no
  `codegen_validation_passed` at all.

  **In the shipped worker image this field is `false` on every calculations job that
  ran codegen** (i.e. wherever `calculations_applied` is `true`; on a budget-skipped job
  the key is absent instead). flake8 is not reachable there — it is not a declared
  dependency of the plugin, and the worker's virtualenv `bin` directory is not on the
  process `PATH` — so the lint subprocess raises `FileNotFoundError`, the lint never
  runs, and a lint that did not run is reported as not passed.
  `codegen_validation_skipped: true` is emitted alongside it, and that marker is how you
  tell "did not run" from "ran and found problems". Do **not** read `false` here as "the
  code-safety gate rejected the generated code" — today it means nothing more than
  "not linted".

  So `true` means, and only means, "the lint ran and found nothing". The field is
  strictly a boolean — it was briefly the string `"skipped"`, which is truthy and so
  still read as "lint clean" to every `if passed:` consumer; that value is gone and will
  not come back. Present only when `calculations_applied` is `true`.
- `calculation_rows: [...]` — an array of computed JSONL rows. Present on any
  `COMPLETED` result for a job that supplied `calculations`, including a budget-skipped
  one, where it is `[]`. (`FAILED` and `CANCELLED` bodies carry no engine blob at all,
  so the key is absent there — see the status bullets above.)

If the sandbox worker fails to execute, the job completes with `success: false` and a
user-safe `error` (e.g., `"Calculation execution timed out"`); the `execution` field
carries the inner error details.

**Budget-skipped calculations — a `success: true` shape with fields missing.** When the
per-job token ceiling is reached before the `code_generator` stage, the job still
completes successfully (the extraction was already paid for and is returned), but:

- `calculations_applied: false`
- `calculation_rows: []`
- **no `execution` key and no `codegen_validation_passed` key** — omitted rather than
  zeroed, because a `{"success": false, "rows_written": 0}` block would read as "ran and
  produced nothing"
- `budget_exhausted: true`, and `budget_skipped_stages` naming `code_generator`

A consumer that reads `result["execution"]["error"]` to find out why calculations are
missing raises `KeyError` on this shape. **Branch on `calculations_applied`**, then read
`budget_skipped_stages` when it is `false`.

**Removed: `calculation_rows_truncated`.** Earlier revisions of this document described
over-cap calculation output as returning `calculation_rows: []` plus
`calculation_rows_truncated: true` on an otherwise successful, fully billed job. **No
code path emits that flag** (grepped across both repos 2026-10-23: the only occurrences
are explanatory comments, one test asserting its absence, and this document). Returning
success with the computed rows silently discarded was the defect, not the contract, so
over-cap output now **fails the job** — in both places it can be detected:

- the sandbox worker fails closed on its own output cap
  (`"execution failed: output exceeds size cap"`, and a sibling row cap), so a
  successful sandbox reply's rows are always inside that cap; and
- the executor's own read guard fails the job with `"extraction failed: calculation
  output exceeded the executor's read cap; raise SANDBOX_MAX_OUTPUT_BYTES on the
  executor to match the sandbox"` — reachable only when the two pods' cap settings
  disagree.

A malformed JSONL row likewise fails the job (`"calculations produced invalid output"`)
rather than being dropped, and so does an output file that cannot be READ at all
(`"calculations produced no readable output; the extraction could not be returned"`) — the engine
reported that codegen ran, so an unreadable file is a real I/O fault rather than an
empty result, and the previous behaviour reported `calculation_rows: []` for it on a
fully billed job with no log at any level.

So `calculation_rows` on a `success: true` job is complete: there is no truncation flag
to check, because there is no truncated success.

**On a failed calculation the extraction is retained inside the executor but does NOT
reach you**, and the error strings say so rather than implying otherwise. They went
through two wrong wordings first, both worth knowing because a consumer may have been
written against either: `"the extraction is in \`data\`"` pointed at a field no caller
can reach, and `"the extraction was kept"` made the same promise one step vaguer
instead of retracting it. They now say **"the extraction could not be returned"**.

What is retained, and where: the document's `record`, `normalized_record` and `keys`
survive the failure inside the executor's own result object rather than being
discarded, because the job was billed for them — and the markers that qualify them
(`extraction_degraded`, `extraction_dropped`, `qa_passed`, `qa_unchecked`,
`qa_partial`, `challenge_passed`, `challenge_unchecked`, `budget_exhausted`,
`budget_skipped_stages`, `document_class`) travel with them, so a salvaged record can
never read as fully validated. They are all dropped before the API: the callback
forwards no `data` on the failure arm, and the finalize view writes only the error. So
a `FAILED` body still carries no engine blob, exactly as the status bullets above say.
The retention exists so that wiring it through is a change to those two hops rather
than a re-extraction; until then, do not write a consumer that expects a partial
record on a failed job.

**Drift from the spec:** §7.3 sketches the failed-job body as
`{success: false, error, timing}`. The shipped body
(`backend/agent_kv/execution_views_result.py::result_payload`) is
`{"success": false, "status": "failed", "error": ...}` — it adds `status` and does
**not** include a `timing` key (there is nothing to time for a job that never produced
an engine result). Document the code: no `timing` on failure/cancellation bodies.

```bash
curl https://api.unstract.example/api/v1/agent-kv/5b6e9b0a-.../result \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

The payload is **keyed by extractor**, with usage attributed per extractor
alongside the authoritative total:

```json
{
  "success": true,
  "status": "completed",
  "extractors": {
    "kv": {
      "success": true,
      "record": {"quotation_number": "Q-10234", "customer": {"name": "Acme Corp"}},
      "normalized_record": {"quotation_number": "Q-10234", "customer": {"name": "Acme Corp"}},
      "keys": [
        {"key_path": "quotation_number", "qa_status": "passed", "challenge_status": "passed"}
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
  },
  "usage_summary": {
    "total": {"pages": 3, "input_tokens": 3120, "output_tokens": 480, "total_cost": 0.0},
    "by_extractor": {
      "kv": {"pages": 3, "input_tokens": 3120, "output_tokens": 480, "total_cost": 0.0}
    }
  }
}
```

`success` and `status` are at the **top level on every terminal payload** —
completed, failed and cancelled — so a client branches on one key. They describe
the job; each extractor keeps its own `success` inside its own block.
`usage_summary.total` is the billing figure; `by_extractor` exists so a
multi-extractor job can be attributed. With one extractor they are the same numbers.
Note the **failed** and **cancelled** payloads above are NOT extractor-keyed: a
failure belongs to the job, not to one extractor.

### `qa_passed` / `challenge_passed`, and the advisory markers that qualify them

`qa_passed` and `challenge_passed` are positive assertions, and on their own they
**cannot distinguish "checked and clean" from "nothing was checked"**. Advisory
markers carry that distinction — the table below is the list; do not count them
from this sentence. They are the whole mitigation, so a consumer that acts on either flag must
read them. They sit in the **same per-extractor block** as `qa_passed` itself
(`extractors.<name>.*`), not at the top level.

**Convention: each marker is present only when it applies, and its absence means the
benign state.** The boolean markers are never emitted as `false` — read a missing key as
`false` (`result.get("qa_unchecked", False)`), not as missing data; for the **two**
list markers — `budget_skipped_stages` and `extraction_dropped` — read a missing key
as `[]` (`result.get("budget_skipped_stages", [])`). An
ordinary clean job's shape is unchanged by any of this, which is why they are omitted
rather than always present.

| Marker | Type | Present when | What it means for the field it qualifies |
| --- | --- | --- | --- |
| `qa_unchecked` | `true` | the token ceiling skipped the `kv_qa` stage | `qa_passed` was left at the much weaker pre-seeded value "every required key was found". No format check, no grounding check and no re-extraction ran. |
| `challenge_unchecked` | `true` | at least one key's **final** value was never challenged | `challenge_passed: true` means "nothing was found wrong about the values that WERE judged", which is not the same as a clean challenge of the record you are reading. |
| `budget_exhausted` | `true` | the per-job token ceiling bit anywhere | Some work the job was asked to do did not happen. |
| `budget_skipped_stages` | `string[]` | the ceiling skipped at least one whole stage | Names the stages that never started, e.g. `["kv_qa", "code_generator"]`. **Never present as `[]`** — see the first edge case below. |
| `qa_partial` | `true` | QA ran and the ceiling bit mid-loop | QA started but abandoned part of its work, so `qa_passed` reflects an incomplete pass. Distinct from `qa_unchecked`, which means the stage never started; the two are mutually exclusive. |
| `extraction_degraded` | `true` | the engine isolated at least one failure | The record may be short through no fault of the document. Paired with `extraction_dropped`; `success: true` with missing keys is otherwise indistinguishable from "the document does not contain them". |
| `extraction_dropped` | `string[]` | alongside `extraction_degraded` | Sorted reason codes for what was isolated. **Closed vocabulary of exactly fourteen values.** Key extraction: `empty_response`, `unparseable_response`, `results_not_a_list`, `results_wrong_shape`, `whole_doc:error`, `page:error`. Array extraction: `array:error` (the fan-out isolated a whole array), plus `array_empty_response`, `array_unparseable_response`, `array_rows_not_a_list`, `array_rows_wrong_shape`, `array_rows_no_declared_column`, `array_tool_args_not_a_dict`. The two `*_wrong_shape` codes mean the response's top-level shape was right and its per-row shape was not — a positional table instead of an array of objects, or a row missing its `key` field — so **some or all** rows were discarded; `array_rows_no_declared_column` means a row matched none of the declared columns, and `array_columns_unmatched` means a declared column appears as a key in **no** row while the model supplied keys nobody asked for — the per-column signal for a renamed or re-cased column, which the row-level one cannot see when only some columns were renamed. Both are judged on key PRESENCE in the model's raw row, never on whether a cell had a value: a declared column that is correctly named and simply empty is a legitimately blank cell and is reported as nothing at all. Classes only, never document content, and counts go to the log rather than onto the wire. An earlier revision suffixed the exception class name (`page:OSError`), which exported a third-party implementation detail as contract; a guard test asserts EQUALITY between this set and what the code emits, across every emitting module, so a new code arrives as a deliberate change to this table. |
| `codegen_validation_skipped` | `true` | the flake8 lint could not run | `codegen_validation_passed: false` means "not linted", not "lint failed". See the calculation result shape above. |

Three edge cases that a reader checking only the happy path gets wrong:

- **`budget_exhausted: true` can arrive with NO `budget_skipped_stages` at all.** The
  ceiling is also checked *inside* the QA retry loop, so a job whose QA loop stopped
  early mid-round has exhausted its budget without any whole stage having been skipped.
  That case now carries **`qa_partial: true`** and omits `budget_skipped_stages`
  entirely; there is no `qa_unchecked` either, because QA did run, just not to
  completion. Read `budget_exhausted` as "something was cut short" and
  `budget_skipped_stages` as "these stages never started" — they are not the same claim.

  **This changed.** An earlier revision emitted `budget_skipped_stages: []` in this
  case — "something is missing, and here is the empty list of what" — and a revision
  before that put the synthetic string `"kv_qa (partial)"` in the list, which no
  consumer testing `"kv_qa" in skipped` matched and which contradicted what the list
  asserts about every other member. A consumer reading the field with the documented
  `result.get("budget_skipped_stages", [])` default is unaffected by the change; one
  that branched on the key being present with an empty value must now read
  `qa_partial`.
- **`qa_unchecked` is not implied by `budget_exhausted`,** and vice versa. Check both.
- **`extraction_degraded` has nothing to do with the budget either.** It means a
  per-page, whole-document or array call failed and was isolated so the rest of the run
  could continue. The job is still `success: true` and still billed, so a consumer that
  treats a short record as "this document has few keys" will be wrong on exactly these
  jobs. Check it before drawing conclusions from absent keys.
- **`challenge_unchecked` has nothing to do with the budget**, and its meaning is
  narrower than it looks. It is set whenever **at least one key's final value was never
  challenged**, which happens on a job with budget left and therefore **no
  `budget_exhausted` marker at all**. A consumer that treats `budget_exhausted` as the
  one "something was skipped" flag will read `challenge_passed: true` on that job as a
  clean challenge. These markers are independent signals; none subsumes another.

  **This is a change in meaning.** An earlier revision described it as "the challenger
  came back with no usable verdict at all" — i.e. no round was ever readable. That left
  two paths unmarked, both of which publish a verdict about a value the record no longer
  holds: a key the challenger REPLACED after judging it, and a key whose later round was
  unreadable so the earlier round's verdict stood. Each key is now decided by the last
  readable verdict that judged **the value it still holds**, and the marker answers the
  question a consumer of `challenge_passed` actually has.

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

Both statuses take the values `"unchecked"`, `"passed"` or `"failed"` — not
`"pass"`/`"fail"`, which earlier revisions of the example above showed. Presence depends
on the entry's `kind`:

- **`kind: "scalar"`** (a `key_path` entry, as above) — `qa_status` is always present;
  `challenge_status` is **omitted when it would be `"unchecked"`**.
- **array entries** (the other shape concatenated into `keys[]`) — **both** are omitted
  when they would be `"unchecked"`.

So read either with a default (`entry.get("challenge_status", "unchecked")`) rather than
by subscript; a missing status means that check never produced a verdict for that entry,
not that the data is absent.

(The exact result shape beyond `success` is the cloud engine's contract — spec §4 — not
re-specified or validated by this repo.)

**The `table` extractor's result** is the table engine's extraction output, filed
under `extractors.table`:

```json
{
  "success": true,
  "status": "completed",
  "extractors": {
    "table": {
      "tables": [{"unit": "A1", "rent": 1200}],
      "page_count": 3,
      "table_pages": [1, 2],
      "headers": ["unit", "rent"],
      "row_count": 1,
      "detected": true,
      "reason": "",
      "timing": {"document_processing": 6.2, "total": 41.7}
    }
  },
  "usage_summary": {
    "total": {"pages": 3, "input_tokens": 3120, "output_tokens": 480, "total_cost": 0.0},
    "by_extractor": {
      "table": {"pages": 3, "input_tokens": 3120, "output_tokens": 480, "total_cost": 0.0}
    }
  }
}
```

`tables` carries one object per extracted row; `headers` is the canonical column list
the engine settled on; `table_pages` are the 1-based pages the rows came from; and
`row_count` is the number of rows extracted. `timing` rides inside the extractor block,
and `parse_failures` appears only when some page failed to parse.

**`detected` / `reason` — why an empty result is empty.** A run that finds nothing is
a *successful* run, and it bills: the detection agents have already been paid for by
the time the pipeline gives up. Two quite different outcomes used to arrive looking
identical — `tables: []`, `row_count: 0`, `success: true`:

* `detected: false` — no page contained a table matching `target_table`, so the run
  stopped **before** extraction. `reason` names the input to change, e.g.
  `"no page contained a table matching target_table='Rent roll'"`. Describe the table
  rather than labelling it: the string is fed to the agent that writes the detection
  prompt, so `"Rent roll with unit, tenant, lease start and monthly rent"` detects far
  more reliably than `"Rent roll"`.
* `detected: true` with `row_count: 0` — the table WAS found and extraction returned
  no rows. `target_table` is not the thing to change here.

A third shape sits between them: detection may have been **incomplete**. A page
whose presence-detection response fails to parse does not abort the run, so
`reason` then reads `detection did not complete: presence detection failed on
page(s) 2; …`, and `parse_failures` is carried out alongside it naming those
pages. Treat that as "unknown", not as "absent" — the table may well be on a page
that was never read.

Both keys are always present, including on a successful extraction (`reason` is then
`""`). The distinction was previously only inferable from which keys were *missing*
from `timing`, which is an internal structure rather than a contract. There is **no
`cost_summary`** on this extractor — the table engine has no per-agent cost tracker — so
`usage_summary` is the only billing figure, as it is for `kv`.

> **`enable_header_mapping` changes the type of `tables`.** With it **off** (the
> default), `tables` is a flat list of row objects, exactly as above. With it **on**,
> the engine wraps them and `tables` becomes
> `{"header_mapping": {...}, "rows": [...]}`. That is a breaking shape change between
> two settings of one option: a client that sets the flag must read `tables.rows`
> instead of iterating `tables`.

## 6. Cancel — `POST /api/v1/agent-kv/{job_id}/cancel`

Defined precisely per spec §7.4: no task-revocation machinery exists anywhere in the
platform, so cancel flips the job row to `CANCELLED` via the same guarded
`mark_terminal` write gate every other terminalization path uses
(`backend/agent_kv/models.py::AgentKVJob.mark_terminal`) — later callbacks/stage
reports become no-ops; a job not yet picked up is dropped at pickup.

A job **already running is stopped cooperatively**, not revoked. Cancellation is
detected opportunistically: the executor only learns of it on its next stage report,
which the internal endpoint answers as a no-op once the row is terminal. Both extractors
check at their engine's progress points — `kv` at every graph-node boundary, `table` at
the engine's own progress points (rate-limited, so detection can lag by a few seconds) —
and the job then terminates as `cancelled`. Work already done is still billed and
metered; work not yet started is not.

**A job that finishes before the cancel is noticed keeps its result.** The
engine flushes OCR and LLM usage *before* the executor's final stage report, so
a cancel colliding with that report lands after the work is paid for. The
extraction is complete and the output fully computed; what used to happen to it
was nothing good, in either of two ways:

- **The ordinary case.** The executor learns of the cancel *from* that final
  stage report (answered as a no-op once the row is terminal) and returns
  success with the full output anyway. By the time the callback worker calls
  finalize, the row has read `CANCELLED` for a whole round trip, so
  `FinalizeView.post` short-circuited on "already terminal" and the output was
  dropped without even being written.
- **The narrow case.** The cancel lands between finalize's own read and its
  `mark_terminal`, so the result *was* written and the guard then correctly
  declined to restatus a terminal row — and the file was deleted as an orphan.

Either way `GET result` reported `{"success": false, "status": "cancelled"}` and
the customer had paid for an answer that no longer existed. Both paths now
attach it to the cancelled row instead
(`FinalizeView._salvage` / `AgentKVJob.attach_result_to_cancelled`) and it is
served as described in [§5](#5-result--get-agent-kvjob_idresult).

A success callback for an already-terminal job is therefore the one case where
finalize writes a result for a row it read as terminal. It is `CANCELLED`-only,
and the conditions are declared once as `AgentKVJob.ATTACH_GUARD` — status
`CANCELLED`, blank `result_ref`, `files_purged` false — then applied twice: as
the filtered `UPDATE` that decides (`attach_result_to_cancelled`), and as a
read `_salvage` takes *first* (`can_attach_result`). The idempotency the
short-circuit protected is unchanged: a duplicate callback attaches nothing.

**The pre-flight read is why a doomed attempt no longer touches storage.**
Writing first and cleaning up afterwards made every redelivered callback — and
every callback arriving after a `DELETE` — write a result file, have the guard
refuse it, and then depend on `delete_result_file`, which is best-effort by
construction: it logs and returns, and no ref is persisted anywhere to retry
from. A single failed delete therefore left extracted customer output in the
bucket with nothing pointing at it, after a purge or past the retention window.
Those cases now read the guard before writing anything.

The read is advisory, not authoritative — a cancel or a competing callback can
still land between it and the `UPDATE`, which is what decides. For that genuine
race, `delete_job_files` reaps the job's own directory once both named files
are confirmed gone, so an unreferenced leftover is collected when the job is
deleted or expires. What that still cannot reach is an orphan created *after*
the row left the TTL candidate set (candidacy comes from the ref columns);
closing that needs a durable marker that outlives the refs.

A **failure** callback for a cancelled job salvages nothing (there is no
result), and a `COMPLETED` or `FAILED` row is never given a second look.

What does *not* change: `status` stays `cancelled`, `completed_at` is untouched,
and `mark_terminal` remains the only way a job reaches a terminal state. The
salvage adds a pointer to work that was already billed; it cannot restatus
anything, and it only ever applies to a `CANCELLED` row (a `COMPLETED` or
`FAILED` row owns its own outcome).

A caller who supplied `webhook_url` has already been sent `cancelled` by then,
so a **follow-up notification** carrying `result_available: true` is delivered
when this happens — see [§8](#8-webhook-delivery).

> **This was reverted three times before it shipped, and the reason is worth
> knowing before you touch it.** `DELETE /api/v1/agent-kv/{job_id}/` guarantees that a
> purged job cannot be resurrected, and it used to guarantee that *by relying on*
> the late finalize deleting its own orphaned write. Keeping the result removes
> exactly that cleanup, and every attempt to rebuild the guarantee from the job's
> own ref columns failed review:
>
> 1. Gate the attach on `result_ref=""` — a purged job could still serve a late
>    result, because `DELETE` blanks both refs and leaves precisely the row that
>    filter matches.
> 2. Also gate on a non-blank `input_ref` — **unsound.** `delete_job_files`
>    deliberately *keeps* a ref whose object delete failed, so TTL cleanup has a
>    handle to retry from; a non-blank `input_ref` therefore does not prove the
>    job was never purged.
> 3. Also re-read the row inside `DELETE` — narrowed the window but left a
>    storage orphan (cleanup can clear a ref it never deleted, and later sweeps
>    select only jobs that still have one, so extracted data outlives its
>    retention window) and left the cancellation webhook un-followed-up.
>
> The common thread: `result_ref`/`input_ref` carry **three** meanings — never
> set, purged, and purge-attempted-delete-failed-retry-later — so purge state
> cannot be inferred from them. What shipped records it instead, on the
> `files_purged` column: written unconditionally by `DELETE` and by TTL cleanup
> before either attempts a delete, read by the attach (which refuses a purged
> row) and by the result endpoint (which refuses to *serve* one, covering the
> surviving-ref case no ref check can see), and both sides take the row lock so
> cleanup cannot interleave between its read and its blanking write.

- Won the race (job was non-terminal): `200` `{"status": "cancelled"}`.
- Already terminal: `409` `{"status": "<job.status>"}`, lowercased (e.g.
  `"completed"`) — consistent with every other `status` value in this API.

  *An earlier version of this document claimed the opposite: that this one field
  carried the raw uppercase enum, and that it was "not a typo". It was wrong.
  `JobCancelView` returns `job.status.lower()`, and the unit test cited as proof
  (`test_job_views.py::test_cancel_on_completed_is_409_and_result_untouched`)
  asserts `{"status": "completed"}`. The e2e lane carried the same wrong
  assertion and had never been run.*

```bash
curl -X POST https://api.unstract.example/api/v1/agent-kv/5b6e9b0a-.../cancel \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 7. Delete — `DELETE /api/v1/agent-kv/{job_id}`

Deletes the result and any residual staged input immediately, blanks the refs whose
objects are confirmed gone, and marks the job `files_purged` (`204`, no body). The job
row itself is retained (audit trail); a later `result` fetch 404s, and status still
works.

A few details that matter if you are changing this endpoint:

- **On a non-terminal job it cancels first**, then purges. Cancelling before the
  deletes is what stops a still-running job from carrying on after its files are
  gone, and from writing a fresh result onto a job the caller has asked to destroy.
- **The `files_purged` marker is written unconditionally** — on every `DELETE`,
  whatever the job's status, and *before* the object deletes are attempted, so a
  delete that fails cannot leave it unset. It records the caller's intent, not the
  outcome. It is what makes "this job was purged" answerable at all: a blank ref
  can equally mean "nothing was ever staged", and a *non*-blank ref can mean
  "purged, but the object delete failed and the ref is kept so TTL cleanup can
  retry" (`storage.delete_job_files`). Nothing downstream may infer purge state
  from the ref columns — see the note in [§6](#6-cancel--post-agent-kvjob_idcancel).
- **A ref whose object delete failed is kept**, deliberately, as that retry handle.
  The response is still `204`: the job is terminal, the intent is recorded, and a
  `5xx` here would only invite a retry of a `DELETE` that already did everything it
  could. The result endpoint refuses such a job on the marker, so a surviving ref
  never becomes a surviving read.
- **It re-reads the row under a lock** (`AgentKVJob.mark_files_purged`) immediately
  before deleting, so a result attached by a late finalize in the meantime is purged
  along with everything else, and one attempted afterwards is refused outright.

```bash
curl -X DELETE https://api.unstract.example/api/v1/agent-kv/5b6e9b0a-... \
  -H "Authorization: Bearer 5c9e2c9e-1234-4a5b-9c6d-abcdef012345"
```

## 8. Webhook delivery

`webhook_url` (if given at submit) receives one terminal-state POST:
`{"job_id": "...", "status": "completed"|"failed"|"cancelled"}` — a fixed payload
shape, no result content (spec §6.7, §7.1).

**The backend owns the terminal notification**, on both paths, and queues it from
whichever request won the terminal guard: `agent_kv_finalized` when a finalize won,
`agent_kv_cancelled` when a cancel did. The two are mutually exclusive, so a job
gets exactly one — and because the enqueue is tied to the guard rather than to an
HTTP reply, losing a response cannot lose the notification. Delivery, retries and
the permanently-undeliverable case belong to the `ide_callback` worker.

> This changed. The finalize notification used to be sent inline by the callback
> worker (`_maybe_webhook`) right after finalize answered. If that *response* was
> lost — a timeout, or a 5xx — the worker retried, the replay found an
> already-terminal row and was told `finalized: false`, and the worker declined to
> send. That was the correct call from where it stood: a non-fresh finalize is
> indistinguishable from the ordinary duplicate callback whose webhook already went
> out. The effect was that the caller was never notified and nothing recorded the
> miss.
>
> The finalize response carries `webhook_enqueued` so the worker never has to
> *assume* which side owns delivery: absent or `false` — which is exactly how a
> backend predating this field answers, and also how a backend whose enqueue
> failed answers — means the worker still sends inline. Transitional, and removable
> once no such backend can be running.

**There is exactly one case of a second POST**, and it is additive:

```json
{"job_id": "...", "status": "cancelled", "result_available": true}
```

It is sent when a cancel that had already been notified turns out to have lost the
race to a finished extraction, so the result was kept and is now readable
([§6](#6-cancel--post-agent-kvjob_idcancel)). Without it a webhook-driven caller —
who has no reason to poll a job they were told was cancelled — would never learn the
answer arrived. `result_available` is the only thing distinguishing it from the
cancellation POST they already have; a bare duplicate would carry no information at
all. It appears on no other notification, so a receiver that ignores unknown keys
simply sees a repeat of the cancellation.

Nothing orders the two POSTs. The cancellation one is queued by the backend the
moment its cancel wins and delivered by a worker; the follow-up is sent inline by
the finalize callback, which is the one notification that is still sent from there
— it is not a terminal transition, so there is no guard for the backend to hang it
on. A receiver can therefore see the follow-up first and then the
plain `cancelled` — treat `result_available` as sticky, not as the state of the
world at delivery time. The result's readability does not depend on either POST
landing: `GET result` is the authority, and this notification only saves a poll.

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
- **Scheme: https-only**, and now refused at SUBMIT rather than only at delivery.
  `send_webhook` exposes a generic `allow_http` escape hatch (for explicitly
  configured dev environments elsewhere), but the Agent-KV caller
  (`_maybe_webhook`) never passes it, so the sink allows https to public hosts
  only. `SubmitSerializer.validate_webhook_url` applies the same rule up front
  with `resolve=False` — a URL the sink could never dial is a 400 on the submit
  instead of a 202 followed by silence. DNS stays off the request thread, so a
  hostname that resolves inward is still caught at the sink rather than here.
- **No redirects** (`allow_redirects=False`).
- **Fixed, minimal payload** (`{job_id, status}`, plus `result_available` on the
  one follow-up described above — never result content) and the **response body is
  never read**: the POST is made with `stream=True` and the response closed in a
  `finally`, so only the status line and headers are consumed. Before that the
  claim was aspirational — `requests` reads the body before returning unless you
  ask it not to — and since this runs inline on the `ide_callback` consumer
  (concurrency 2, shared with Prompt Studio), a receiver returning a huge or
  trickled body could hold one of those slots indefinitely.
- **Timeouts are per-socket-operation, not total** — 5 s connect, 10 s read. That
  is a `requests` property, not a choice: a peer that keeps trickling resets the
  read budget on every chunk. The body is never read (above), which removes the
  unbounded case; a server that trickles *headers* can still extend one delivery.
  The structural fix is to move delivery onto the `notifications_webhook` worker
  the way pipeline notifications do, so a slow receiver cannot occupy an
  `ide_callback` slot at all — not done here, because it is a queue change.
- **Terminal notifications retry; the one follow-up does not.** This changed
  when the backend took ownership of the terminal POST. `agent_kv_finalized`
  and `agent_kv_cancelled` are queued tasks with `autoretry_for=(Exception,)`
  and `max_retries=3` (backoff, jitter): `_deliver_terminal_webhook` RAISES on
  a connection failure or a non-2xx, so the delivery is retried. A URL the
  SSRF guard refuses permanently is the exception — retrying cannot change a
  property of the URL, so it is logged at ERROR and the message acknowledged.

  The `result_available` follow-up, still sent inline by the callback worker,
  is the one delivery with **no retry**: a failure there is logged and
  swallowed. It is also the one that matters least — `GET result` is the
  authority, and the notification only saves a poll.

Test/dev stacks only: `AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1` on the
ide-callback worker waives both guards (http scheme and non-public host) so the
e2e lane can deliver to a receiver on the compose host. Never set it in
production.

## 9. Retention and TTL

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
  against an already-`CANCELLED` job does not trigger it either: it never wins the
  terminal guard, and `_drop_staged_input` stays gated on a won guard, so even the
  success callback that *does* store a result there
  ([§6](#6-cancel--post-agent-kvjob_idcancel)) leaves the input alone. A cancelled
  job's staged input is therefore cleaned up the ordinary way: by the TTL sweep once
  `expires_at` passes, or by an explicit `DELETE /api/v1/agent-kv/{job_id}`.
- **Result retention**: `AGENT_KV_RESULT_TTL_DAYS` (default **7** days, D10's
  engineering default) — results are re-readable until then, then swept by the
  internal `ttl-cleanup` endpoint ([§6](#11-deploy-checklist)), which blanks
  `result_ref` (and `input_ref` too, covering the cancelled-job case above, or
  defensively for any input that somehow outlives completion). The job row itself is
  never deleted (audit trail persists past TTL, only the object-store payloads are
  dropped).
- **TTL cleanup marks every row it processes `files_purged`**, on the same terms as
  `DELETE` ([§7](#7-delete--delete-agent-kvjob_id)): before the deletes are
  attempted, and whether or not they succeed. The sweep *is* a purge, so it owes
  that marker — and without it, a result attached to a cancelled row by a late
  finalize could land after the sweep had read the row and before it blanked the
  refs, leaving the object in storage with its ref cleared. Since the sweep's own
  candidate filter is `input_ref > "" OR result_ref > ""`, a row blanked that way
  can never be reconsidered: extracted customer data past its retention window with
  nothing pointing at it. The marker plus the row lock
  (`AgentKVJob.mark_files_purged`) is what closes that.
- **A row whose object delete failed keeps its ref and is retried** from a reserved
  slice of each later batch (`cleanup_failed_at`, see `maintenance.run_ttl_cleanup`).
  Such a row is already `files_purged`, so the API treats it as purged while cleanup
  is still working on the bucket — which is the point: the two facts are separate and
  are recorded separately.
- **`expires_at` is stamped at submit time**, not at completion —
  `SubmitView.post` sets `expires_at = timezone.now() + timedelta(days=AGENT_KV_RESULT_TTL_DAYS)`
  before dispatch even runs. **This is a real divergence from spec D10's framing**
  ("results retained 7 days" implicitly from completion): for a job that runs close to
  its `timeout` ceiling, the effective post-completion retention window is slightly
  under the full 7 days. Documented here as shipped behavior, not silently
  reconciled — flagged for anyone tightening D10 later.

## 10. When the engine is unavailable (501 behavior)

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
`POST /api/v1/agent-kv/` on an OSS-only deployment therefore returns:

```json
{"detail": "agent-kv engine not available on this deployment"}
```

with HTTP `501`. Key management and status/result/cancel/delete on
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
   outcome it has — success or failure, it does not matter which: at pickup there is
   no result yet, so the status write no-ops either way.

   *A `noop` on a LATER stage report is a different situation and the executor should
   not conflate them.* By the final report the work is done and paid for, and a
   success body carrying the full output is then stored on the cancelled job rather
   than discarded ([§6](#6-cancel--post-agent-kvjob_idcancel)). So "report whatever
   you have" is right at both ends of the run, but for different reasons: at pickup
   because nothing can be lost, and at the end because something can.

Step 2 is not optional. `FinalizeView`'s terminal-state guard (spec §5.4) correctly
no-ops the status write for an already-terminal job — but its concurrency-slot
release (`AgentKVConcurrencyLimiter.release`) lives in a `finally`, unconditional on
whether the guard actually won ([§6](#9-retention-and-ttl) covers the input-deletion
side of this same guard). An executor that treats `noop: true` as "nothing left to do
here" and skips the finalize call entirely leaks that job's concurrency slot for the
rest of the limiter's TTL (6 hours) instead of releasing it immediately. This is the
entire mechanism behind a pre-pickup cancel actually being observed and cleaned up
promptly — there is no other signal.

## 11. Deploy checklist

Everything below is required (or worth checking) to run this feature for real,
beyond `docker compose up`:

1. **Cloud plugin**: install/enable the `agent_kv` backend capability plugin
   (probed via `plugins.get_plugin("agent_kv")`) — without it, submit always 501s
   ([§6](#10-when-the-engine-is-unavailable-501-behavior)). This repo ships gated
   dark by design; nothing to do for an OSS-only deployment except accept the 501.
   The marker the probe keys off is the mere presence of
   `backend/plugins/agent_kv/__init__.py` — a cloud image ships it (via the
   plugin-copy step), an OSS-only build does not.
2. **Executor worker fleet queue — nothing to add for this release.** The dispatcher
   derives the queue name from the EXECUTOR name as `celery_executor_{executor_name}`
   (`unstract/sdk1/src/unstract/sdk1/execution/dispatcher.py`), and this deployment
   routes `table` only, to the **`agentic_table`** executor
   (`EXTRACTOR_ROUTES`, `backend/agent_kv/constants.py`). So the queue this API
   actually uses is **`celery_executor_agentic_table`**, which every fleet already
   drains: it is in `workers/run-worker.sh`'s executor default list, and in
   `workerPgExecutor.env.WORKER_PG_QUEUE_CONSUMER_QUEUE` in the cloud chart.

   > **Do not add `celery_executor_agentic_kv`.** Earlier revisions of this checklist
   > told operators to, and it is wrong in this release: `kv` is not routable
   > (§1), nothing produces to that queue, and nothing consumes it. The chart asserts
   > its absence deliberately — `AKV-Q5b` in
   > `charts/unstract-platform/unittests/agent_kv_wiring_test.yaml` fails the build if
   > the name appears anywhere in the chart, because a queue with a consumer and no
   > producer wastes a fleet lane, and one with a producer and no consumer accepts
   > work and drains nothing with no error anywhere. It becomes the right queue only
   > when `kv` is re-enabled in `EXTRACTOR_ROUTES`, and
   > `backend/agent_kv/tests/test_queue_wiring_is_derived.py` derives the expectation
   > from that constant so the two cannot disagree.

   Note the knob name too: since Celery was removed (UN-4078) the deployed fleet is
   the PostgreSQL queue consumer, so the setting that matters is
   **`WORKER_PG_QUEUE_CONSUMER_QUEUE`**, not `CELERY_QUEUES_EXECUTOR`. Both fleets
   also carry `additionalConfigs: [..., agentKv]`
   (`charts/unstract-platform/values.yaml`, cloud repo) so the executor pods get the
   `AGENT_KV_*` LLM/LLMWhisperer env alongside the queue wiring.
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
   of registering a `PgPeriodicTask` row.

   **The CronJob is the only owner.** Migration `0004_pg_periodic_tasks` once also
   seeded two `PgPeriodicTask` rows for the same two tasks. `0007` deletes them and
   `0009` finishes the job; the paragraph below is why it takes two.

   The rows were seeded `pg_owned: False`, and `0007` scoped its delete to that flag
   so a self-hosted operator who had deliberately adopted them was not stranded. The
   premise was that only a human ever sets `pg_owned: True`. **It is not.** The cloud
   chart's `backend.pgScheduleMirror` hook runs `converge_pg_scheduler --periodics` on
   every install, upgrade *and* rollback; that calls `mirror_pg_periodic_tasks --adopt`
   with no names, which is `PgPeriodicTask.objects.all()`; and
   `templates/validate-pg-worker-fleet.yaml` refuses to render with the hook off, so
   it is not optional. Putting a row in `pg_periodic_task` on a chart-managed
   deployment *is* asking the PG scheduler to own it — which is the mechanism
   `dashboard_metrics` relies on, and the reason `0004` should never have used it for
   schedules the chart was already running as CronJobs.

   Deploying snapshot.415 to a dev namespace found both halves live: `agent_kv_sweep`
   at `pg_owned=t` with `last_run 11:00:02 / next_run 11:10` under the PG scheduler,
   alongside the CronJob's `*/15` tick — the `:30` collision the chart's offset comment
   says it avoids, and ttl-cleanup disagreeing with itself 24x (daily on the row,
   hourly on the CronJob). `0007`'s guard spares precisely the rows that are
   double-firing, so `0009` repeats the delete by name alone. It has to be a new
   migration: `0007` is recorded as applied wherever the problem exists, and Django
   never re-runs it.

   Note also that `pg_owned: False` is not a stable state on a chart-managed
   deployment — the next `helm upgrade` adopts the row again — so deleting the row is
   the only end state that holds. Only the CronJob side carries
   `concurrencyPolicy: Forbid` and a deadline.

   > **Self-hosted OSS: you must schedule these two yourself.** There is no CronJob
   > outside the cloud chart and no migration registers them any more. Run
   > `manage.py agent_kv_sweep` and `manage.py agent_kv_ttl_cleanup` from cron, a
   > systemd timer, or your own `PgPeriodicTask` rows with `pg_owned: True` — the
   > scheduler proxy tasks `agent_kv.sweep`/`agent_kv.ttl_cleanup` are still
   > registered and still work. `0009` cannot delete rows you create, because it is
   > already recorded as applied by the time you create them; and on an on-prem helm
   > install (`agentKvCronJobs.enabled: false`) the schedule-mirror hook adopting them
   > is exactly what you want, since nothing else fires them. Create them under your
   > own names if you would rather not share names with a retired migration.
   > Without them a stranded job holds its concurrency
   > slot until the 6 h Redis TTL, and `AGENT_KV_RESULT_TTL_DAYS` is advisory:
   > staged documents and results stay in the bucket indefinitely, which is a
   > retention failure, not just a disk-usage one.
   >
   > Note this deployment routes `table` only, and that extractor needs the cloud
   > `agentic_table` plugin — so a pure-OSS install cannot dispatch an Agent-KV job
   > at all, and has no stranded rows to reap until it ships an engine plugin.

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
   see [§6](#12-environment-reference) and `docker/sample.env`.

   > **For the `table` extractor, the executor-side credential group below must be
   > left UNSET — not merely "is not required".** That path resolves the caller's
   > own platform adapters (see §3a), so none of the six `AGENT_KV_LLM_*` /
   > `AGENT_KV_LLMWHISPERER_*` values is read on it. The group only has to be
   > configured where the `kv` extractor is deployed, which is a separate release
   > track. A table-only deployment leaves
   > `global.sharedConfigs.agentKv.enabled: false` and the API works.
   >
   > **Deploy order: cloud worker first, then the backend.** The two repos deploy
   > independently and nothing on the wire marks the capability. A new backend
   > against an *old* worker sends validated `adapters` in `executor_params` to a
   > worker that has no `ParamKeys.ADAPTERS`; it ignores the key and calls
   > `ExtractionConfig.from_env()`. If those six values are set it runs on
   > **operator** credentials, bills the `agent_kv:{provider}/{model}` sentinel, and
   > returns a 202 with a correct-looking result — while the adapters the caller
   > named were never used. Nothing in either repo's logs reveals it. With the group
   > unset the same old worker fails loudly with "Missing required Agent-KV env
   > vars", which is what a half-finished rollout should look like. The reverse
   > order is safe by construction: the new worker hard-fails "Missing required
   > adapters" rather than falling back to env.
   >
   > Two operator knobs are still read on the table path, independently of that
   > group: `AGENT_KV_STORAGE_DIR_PREFIX` (which must match the backend's — the
   > executor derives the job's expected directory from it to enforce the tenant
   > boundary on the staged input) and `AGENT_KV_PARALLEL_PAGES`.

   The executor-side vars
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

    Every scenario whose submit must be ACCEPTED also needs the three adapter
    ids exported — `AGENT_KV_E2E_LLM_ADAPTER`, `AGENT_KV_E2E_LITE_LLM_ADAPTER`,
    `AGENT_KV_E2E_X2TEXT_ADAPTER` — since `table` submits name the caller's own
    platform adapters (§3a) and the API validates each against the Bearer key's
    organization. Create them once in the target org (an LLM adapter, a cheaper
    LLM adapter, and an LLMWhisperer X2TEXT adapter). Without them those
    scenarios skip rather than fail.

    Two scenarios are operator-gated on top of that: the bad-credential
    scenario (`AGENT_KV_E2E_BAD_LLM_ADAPTER`, the id of an LLM adapter
    deliberately carrying an invalid provider credential — see the test module
    docstring; it replaces the removed `AGENT_KV_E2E_BAD_KEY_JOB`, which this
    path no longer reads) and the
    completion-webhook scenario, which needs
    `AGENT_KV_WEBHOOK_INSECURE_ALLOW_HTTP_PRIVATE=1` set BOTH on the
    ide-callback worker (it waives the webhook SSRF guards — https scheme +
    public host — for test/dev stacks only; never set it in production) and in
    the pytest process env; the receiver is reached via
    `host.docker.internal` (the compose host-gateway mapping). The lane also
    covers sync-wait submits (`timeout` → 200 with the inline result) and an
    `.xlsx` document (`fixtures/invoice.xlsx`, the no-pre-OCR-page-count path).
11. **Sandbox worker — calculations codegen fleet. NOT APPLICABLE TO THIS
    RELEASE; do not action this item.** `calculations` belongs to the `kv`
    extractor, and `EXTRACTOR_ROUTES` accepts only `table`, whose options
    reject the field — so no job this release can accept reaches the sandbox,
    whatever `AGENT_KV_CALCULATIONS_ENABLED` is set to. No sandbox fleet ships
    here, and deploying one buys nothing until `kv` is routable.

    Kept because it is the deployment order to follow WHEN that happens, and
    the order is the part that is easy to get wrong. Everything below is
    future KV-only work.

    The optional `calculations` field
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
    the extracted record in-memory. This no-secrets/deny-all-egress posture is the
    **Kubernetes/chart deployment guarantee**. The reference `docker-compose.yaml`
    included here is a best-effort dev mirror only, not that guarantee: its
    `worker-sandbox` service shares the same full worker env-file (`workers/.env`) as
    every other worker for operational simplicity, so on that stack the untrusted-code
    boundary is the runner's per-subprocess env scrub (spec §6.3 layer 2), not full
    pod-level secret isolation — don't run untrusted `calculations` against secrets you
    care about on docker-compose. User-supplied `calculations` expressions are
    validated through an AST gate (layer 1 of a 5-layer defense-in-depth model) at
    submit time before ever reaching the sandbox, and further constrained (parsing,
    type-checking, capability allowlist) at execution time. The AST gate is a
    **best-effort** layer-1 control — a fail-closed denylist that closes the cheap,
    demonstrated bypasses and raises the cost of the rest, not a provably airtight
    sandbox by itself. The *enforced* containment is layers 2–5: the runner's
    env-scrub + rlimits (layer 2) and the pod's non-root/read-only-rootfs/no-secrets/
    deny-all-egress/per-job isolation (layers 3–5), with `runtimeClass: gvisor` as the
    deferred syscall-sandbox mitigation (see the accepted v1 residual below). Do not
    treat an AST-gate pass alone as proof generated code is safe.

    **Accepted v1 residual (in-pod file reads):** because generated code
    legitimately needs the `open()` builtin for its input and output files, untrusted
    calculation code can read a world-readable file inside its own sandbox pod and
    return the contents to the submitter. The import allowlist is exactly `{json, math,
    statistics, decimal, datetime, re, collections, itertools, functools, sys}` —
    `pathlib`, `os`, `io`, `socket` and `urllib` are all outside it, so this is a single
    read of a known path, not directory traversal and not an exfiltration path. This is contained — not by the AST gate, but
    by the pod's layers 2–5: no secrets in the pod (not even the platform
    `ENCRYPTION_KEY`), non-root on a read-only rootfs, default-deny egress (no
    exfiltration), per-job isolation, and results returned only to the submitting
    key — so the worst case is disclosure of a non-sensitive container file to the
    customer who submitted the job. The deferred hardening for this is a
    `runtimeClass: gvisor` sandbox. Consequently the sandbox pod's default-deny egress
    and no-secrets posture are load-bearing and must not be relaxed.

## 12. Environment reference

All `AGENT_KV_*` settings (`backend/backend/settings/base.py`), each `os.environ.get`
with the default shown:

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_KV_PATH_PREFIX` | `api/v1/agent-kv` | Top-level public URL prefix (whitelisted past tenant middleware). |
| `AGENT_KV_MAX_FILE_SIZE_MB` | `50` | Submit-time file size cap. |
| `AGENT_KV_ABANDONED_SLOT_GRACE_SECONDS` | `3600` | How long after CANCELLATION a cancelled job's executor is presumed dead, so the sweep's phase 3 may release the concurrency slot it still holds. Must stay **below** `rate_limiter.SLOT_TTL_SECONDS` (6 h) or the window is empty and the phase silently releases nothing. |
| `AGENT_KV_MAX_PAGES` | `100` | Pre-OCR cap on the pages of the DOCUMENT for PDFs — checked against `pages_total`, **not** against the `page_start`/`page_end` range (§6.1), because the whole file is OCR'd and billed whatever the range. The cloud worker refuses on the same quantity. Excel has no pre-OCR page concept, so it takes the engine's post-OCR virtual-page cap instead; images are not accepted. |
| `AGENT_KV_MAX_CALCULATIONS_BYTES` | `20000` | Byte cap on the optional `calculations` field. |
| `AGENT_KV_MAX_SCHEMA_BYTES` | `262144` | Byte cap on the raw `keys` JSON document (256 KiB). |
| `AGENT_KV_RESULT_TTL_DAYS` | `7` | Result retention window (and a cancelled job's input, which rides the same TTL — a completed/failed job's input is deleted immediately at finalize instead), stamped at submit time (see [§6](#9-retention-and-ttl)). |
| `AGENT_KV_MAX_TIMEOUT_SECONDS` | `300` | Upper bound on the submit `timeout` (synchronous-wait) field. |
| `AGENT_KV_CONCURRENT_LIMIT` | `5` | Per-organization concurrent in-flight job cap (own Redis namespace). Fails **closed** (429) when Redis is unreachable — see `AGENT_KV_LIMITER_FAIL_OPEN`. |
| `AGENT_KV_KEY_RATE_LIMIT_PER_MINUTE` | `60` | Per-key request rate limit (submit + validate). Fails **closed** (429) when Redis is unreachable — see `AGENT_KV_LIMITER_FAIL_OPEN`. |
| `AGENT_KV_LIMITER_FAIL_OPEN` | `false` | What both limiters above do when Redis is unreachable. Default `false` = fail **closed**: the request is refused with a 429. Set `true` to restore the old fail-open behaviour, where an unreachable Redis removed the concurrency ceiling **and** the per-key rate ceiling at once while the API went on accepting billable work — a state that cannot be observed from the outside. A 429 is recoverable by the caller; an unbounded fan-out is not. |
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
