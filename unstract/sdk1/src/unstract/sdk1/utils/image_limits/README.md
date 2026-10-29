# Vision image-request limits (`image_limits`)

Image output mode sends every page image of a document to a vision LLM in
one request. Each provider caps that request differently, and none of it is
in litellm's registry, so Unstract maintains the table in `limits.json` and
resolves it here.

## What the table holds

- `default`: the conservative fallback (20 images, 20 MB wire, 1,500
  tokens/page). It fills a provider's null count/byte/token fields. On hosted
  providers that is a hard cap; on `kind: pass_through` providers (Ollama,
  OpenAI-compatible servers, NVIDIA Build, unknown OpenRouter upstreams) it
  is advisory: the policy logs what the default would have been and sends
  the request.
- `providers.<key>`: `adapter` (the llm1 adapter), `display_name`, `kind`,
  `defaults` and ordered `model_overrides`. Each limit field is
  `{value, confidence, source, scope?, base64_counted?, note?}`; `source`
  keys into `sources`, which carries the URL, quote and `verified_on`.
- Byte values are decimal (1 MB = 1,000,000). `base64_counted: true` (or
  absent) means the provider measures the encoded body; the policy converts
  that to a raw-byte budget. `false` means raw bytes.

## Lookup rules (enforced by `_schema.py` and `resolve.py`)

This is the one statement of the matching rule; the code and
`limits.json` point here.

1. Provider key = the adapter's `get_provider()`, except a Bedrock model
   validated to `bedrock_mantle/...` uses `bedrock_mantle`. Never the
   litellm prefix alone: MiniMax may send `anthropic/<id>`. A provider the
   bundled table has is always resolved, from the bundled entry if the
   effective table lacks it (one WARNING per provider per process), and
   keeps the bundled `kind` (a remote copy's `kind` is clamped, see rule
   7); only an operator override file can change a `kind`. The same holds
   for an `inherit` parent: an override-file entry inheriting from a
   provider the remote copy dropped resolves that parent from the bundled
   entry.
2. Candidates are the bare (litellm-prefix-stripped) ids in this order:
   `cost_model` (Azure's real model), the validated model, then extra ids
   (Bedrock `model_id` behind an ARN).
3. Overrides are tried IN TABLE ORDER; each one is tested (`re.search`,
   patterns carry `(?i)`) against every candidate. The first override that
   matches ANY candidate wins, so an earlier override matching only an
   extra id beats a later one matching the model. Its fields replace the
   provider defaults field by field. `inherit` takes another provider's
   resolved limits for the rest of the matched candidate (OpenRouter).
4. A field still null after that: `max_images_per_request`,
   `max_request_bytes` and `tokens_per_image` fall back to `default`
   (advisory on `kind: pass_through` providers); per-image fields mean
   "no check".
5. The Anthropic 100-vs-600 split comes from our own 200k-model regex, not
   litellm's `max_input_tokens` (which is wrong for Sonnet 4.5). The regex
   accepts `-` or `.` between version digits (OpenRouter's
   `claude-sonnet-4.5`) and is repeated on anthropic, vertex_ai, azure_ai
   and bedrock_mantle.
6. Resolution never reads `litellm.model_cost`, so the remote and bundled
   cost maps resolve the same validated string identically. Only
   `local_max_input_tokens` reads the in-process registry (litellm's remote
   cost map, unless `LITELLM_LOCAL_MODEL_COST_MAP` pins the bundled one);
   it never makes a per-lookup network call.
7. Remote clamp. When the base table is the remote copy, every lookup
   (`resolve_image_limits`, so the
   `LLM` accessors and every consumer built on them, `refresh=False`
   reads included) also resolves the same inputs (provider, model,
   `cost_model`, extra ids) against the bundled table and combines them,
   for a provider the bundled table knows:
   - `kind` is the bundled one, and the advisory flag of every
     default-filled field follows that kind;
   - `max_images_per_request`, `max_request_bytes`, `max_image_bytes`,
     `max_image_px`, `many_images_threshold` and `many_images_max_px`
     (`GUARDED_FIELDS`) are `min(remote, 2 x bundled)`
     (`MAX_REMOTE_RAISE_FACTOR`), byte limits compared as raw bytes so
     `base64_counted` differences count. A raised or removed
     `many_images_threshold` counts as loosening. A bundled value that is
     unknown or advisory leaves the remote value as it is; a remote value
     that is not enforced counts as unlimited. Tightening always passes.
   A capped value carries `clamped=True`, `clamped_from` (the remote
   value, or None when the remote value was not enforced) and
   `confidence: unverified`; `format_limit_source`
   says it was capped, and the process logs one WARNING per (provider,
   model, field) with both numbers, so a maintainer can see that main is
   being clamped. A provider the bundled table does not know uses the
   remote data as-is. Fields and provider entries that come from the
   operator override file (layer `override`) are never clamped; the
   override applies after the clamp's remote layer. `max_image_patches`,
   `tokens_per_image` and `max_input_tokens` are not clamped (product
   decision, UN-4427): a remote copy may change them freely.

## Checks (`policy.py`)

`compute_page_budget` = min(image count, LLMWhisperer's 999, operator
ceilings). `ImageModePolicy` adds the raw-byte budget, per-image byte/pixel
limits and the Anthropic ">20 images ⇒ ≤2000 px" rule (kept per model, the
strictest of each across several LLMs, each naming the model it came from);
`check_page_set` applies them to a page set. Tunables are module constants:
`PROMPT_TOKENS_RESERVE`, `ENFORCE_PER_IMAGE_LIMITS`, `TEXT_RESERVE_BYTES`,
`ASSUMED_PAGE_BYTES` (pre-conversion size advisory only, never a rejection)
and `PASS_THROUGH_DEFAULTS_ARE_ADVISORY` in `resolve.py`.

The context-window term ((context − reserve) / tokens per page) is WARN
ONLY. Its tokens-per-page figure is an estimate whether it is the default
(1,500, which would have held 128K gpt-4o to 82 pages) or a model's own
entry (Claude 4.7+: ~2,850 per 150-DPI page), so it never rejects a
document: the policy warns when the pages may not fit, and the provider's
context-length error stays the backstop. Image count and byte limits are
enforced.

Advisories (that warning, pass-through defaults, the pre-conversion size
hint) go to the worker log at WARNING and, through
`ImageModePolicy.with_advisory_sink`, to the user's run log at WARN.

### Rollout bound: `LEGACY_ANSWER_BOUNDS_ACTIVE`

While `policy.LEGACY_ANSWER_BOUNDS_ACTIVE` is `True` (the UN-4427 rollout,
until the cloud answer plugin uses model-aware limits) every model-aware
policy is ALSO held to the legacy 90 pages / 14 MiB, through
`extraction_bound_kwargs()` and the legacy accessors `configured_page_cap()`
/ `configured_max_total_bytes()`. So a generous model (Gemini, OpenAI) is
still capped at 90 pages; only stricter models (Bedrock 20, Mistral 8, ...)
see their own, lower limits. In this mode `VLM_IMAGE_ANSWER_PAGE_CAP` and
`VLM_IMAGE_ANSWER_MAX_TOTAL_MB` (MiB) REPLACE the 90 / 14 MiB, so a value
above them raises the bound for larger models.

Once the flag is off, the same env vars are read by
`configured_page_ceiling()` / `configured_request_bytes_ceiling()` and only
ever tighten a model's limits; unset means no ceiling. An invalid value is
logged at ERROR and keeps the legacy default (90 / 14 MiB), never "no
ceiling".

### Runtime switch: `VLM_IMAGE_LIMITS_ENFORCE`

`VLM_IMAGE_LIMITS_ENFORCE=false` (also `0`, `no`, `off`) turns the
model-aware checks off without a deploy of new data. The switch is honoured
inside sdk1's builders, so every consumer gets it without checking it:
`ImageModePolicy.from_limits`, `compute_page_budget` and
`extraction_bound_kwargs()` then yield the fixed 90-page / 14 MiB cap
(`ImageModePolicy.fixed_cap()`, the pre-UN-4427 behaviour) whatever limits
they are given — extraction, the Prompt Studio upload and cache-hit
checks, and the cloud answer plugin and its profile summary alike. (The
extraction worker and the Prompt Studio upload and cache-hit checks also
test it first, to skip the LLM lookup, and then apply the fixed page cap.) Set it on the backend and every worker. Unset or `true` keeps
model-aware limits; any other value is logged at ERROR and keeps them on.

## Where the table comes from

The source of truth is `limits.json` in this directory on the `main`
branch of Zipstack/unstract. By default a process uses the copy bundled in
this package and fetches nothing, so an on-prem install never phones home
and its limits change only with an sdk1 release. A deployment that wants
data fixes without a release (SaaS) opts in by setting
`VLM_IMAGE_LIMITS_URL` to the published file (`PUBLISHED_LIMITS_URL`).
Each process uses, highest precedence first:

1. `VLM_IMAGE_LIMITS_FILE=/path/to/override.json` — an operator file in the
   same schema, applied on top of the base table. A provider present in it
   replaces that entry wholesale (no deep merge); a `default` block is
   merged field by field over the shipped default (it may not null a
   defaultable field); `sources` are merged. Its `inherit` targets and
   source keys may name any provider or source of the base table or of the
   bundled one, so a provider or source dropped from the remote copy does
   not invalidate the file. Each process re-reads the file when its
   modification time or size changes, so editing or replacing it (e.g. a
   remounted ConfigMap) needs no restart. A malformed or unreadable file is
   logged at ERROR and ignored, and retried when it changes or after 60
   seconds (`OVERRIDE_RETRY_SECONDS`). A future per-org override would plug
   in here.
2. The remote copy — only when `VLM_IMAGE_LIMITS_URL` is set (unset or
   empty, the default, means no fetch). The published file is
   `https://raw.githubusercontent.com/Zipstack/unstract/main/unstract/sdk1/src/unstract/sdk1/utils/image_limits/limits.json`
   (the backend and workers `sample.env` list it).
3. The copy bundled in this package, always available.

No caller waits on GitHub (`source.py`):

- `get_limits_table()` always answers from memory: the last good remote
  copy this process holds, else the bundled one. When a refresh is due it
  starts one on a background daemon thread and returns at once; while it
  runs, every caller keeps serving the last good table;
- at most one attempt per process per `VLM_IMAGE_LIMITS_REFRESH_SECONDS`
  (default 3600, floor 60), and a failed attempt also waits for the next
  window;
- each attempt has an overall 3-second deadline (`FETCH_TIMEOUT_SECONDS`)
  covering DNS, connect, headers and body, does not follow redirects, and
  is capped at 1 MB (`MAX_REMOTE_BYTES`);
- `get_limits_table(refresh=False)` (and
  `LLM.image_input_limits_for(..., refresh_table=False)`) never even starts
  a refresh.

The remote file must pass the same strict validation as the bundled one,
including `_meta.schema_version` equal to the version this sdk1 reads and
override patterns of at most 300 characters (`MAX_PATTERN_LENGTH`) that
compile. Beyond that the file is accepted as a whole: what a data refresh
may change is enforced per lookup by the remote clamp (Lookup rules,
rule 7), because a merge to main reaches every fetching install within an
hour. A provider missing from the remote copy resolves from the bundled entry,
also as the `inherit` parent of an operator override-file entry.
Checking the table as a whole could not do this job: it cannot enumerate
model ids nobody listed (a new override can shadow any real model), and
rejecting the file would also hold an older install back from every later
fix in it. With the clamp, one over-raised value is capped and the rest of
the file (tightening, new providers) still applies. A model newly listed
under a provider the bundled table already has is clamped too: the bundled
table resolves that model id from the provider's defaults (or the shipped
`default`), so its count and request bytes can be at most 2x that value
until an sdk1 release bundles the entry (rule 7).

A timeout, HTTP error, invalid JSON or a file that fails validation logs a
warning and keeps the last good copy (the previous remote table, else the
bundled one); nothing in the fetch path raises.

Every table records its origin. The log says which copy is in use
(source, URL or path, schema version, `_meta.verified_on`, sha256 prefix),
and `ImageRequestLimits.table_version` (e.g. `2026-10-09 remote
1a2b3c4d5e6f`) is appended by `format_limit_source` to user-facing errors
and to the run-log summary.

## Maintaining the data

1. Change a number only with a source: add or update the `sources` entry
   (URL, quote, `verified_on`), set `confidence: verified` only when the
   page states the number for that scope.
2. Probe before trusting an `unverified` value: send N and N+1 images to
   the model; record the result in the note.
3. Order overrides by the lookup rule above (first override matching any
   candidate wins, so put specific patterns first) and repeat every field
   that differs from the provider defaults.
4. Run `pytest tests/test_image_limits_*.py`: the table test rejects
   unknown keys, unresolved sources, bad regexes and missing providers.
5. The dataset's research and verification log live outside the repo
   (`claudedocs/vlm-consumer/model-limits/`); `_meta.source_dataset`
   points at them.
6. Merging a change to `main` publishes it: every install with fetching
   on (`VLM_IMAGE_LIMITS_URL` set, e.g. SaaS) picks it up within one
   refresh window, without a release; installs on the default (no URL)
   get it with their next sdk1 release. Review a
   data change as you would a deploy. Installs clamp what main may
   loosen (Lookup rules, rule 7): a removed provider resolves from the
   bundled entry (directly, and as the `inherit` parent of an operator
   override file's entry, which stays valid), a changed `kind` keeps the
   bundled one, and a guarded limit (image count, request bytes,
   per-image bytes and pixels, and the many-images rule) above 2x the
   bundled value for the same model is capped at 2x (a WARNING per provider, model and field names
   both numbers). Ship those changes in an sdk1 release. Lowering limits
   and adding providers takes effect on refresh. A model newly listed
   under a provider the bundled table has is clamped against what the
   bundled table resolves for it (the provider's defaults or the shipped
   `default`), so a generous new entry is capped at 2x that until it ships
   in a release. `max_image_patches`, `tokens_per_image` and
   `max_input_tokens` are not clamped, so review them with extra care.
7. Keep the schema backward compatible. Older installs reject any file
   they cannot read and stay on their bundled copy, so a key they do not
   know (a new limit field, a new field attribute) cuts them off from
   every later data fix. Data-only edits (numbers, sources, notes, new
   providers or overrides using existing fields) keep
   `_meta.schema_version` unchanged. A change that needs a new key or a
   new meaning bumps `schema_version` and ships in an sdk1 release that
   reads it; until installs upgrade they keep using their bundled table.
