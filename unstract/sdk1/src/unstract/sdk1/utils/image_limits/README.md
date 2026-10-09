# Vision image-request limits (`image_limits`)

Image output mode sends every page image of a document to a vision LLM in
one request. Each provider caps that request differently, and none of it is
in litellm's registry, so Unstract maintains the table in `limits.json` and
resolves it here.

## What the table holds

- `default`: the conservative fallback (20 images, 20 MB wire, 1,500
  tokens/page). It fills a provider's null count/byte fields. On hosted
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

1. Provider key = the adapter's `get_provider()`, except a Bedrock model
   validated to `bedrock_mantle/...` uses `bedrock_mantle`. Never the
   litellm prefix alone: MiniMax may send `anthropic/<id>`.
2. Strip the litellm prefix; try overrides (`re.search`, patterns carry
   `(?i)`) against the bare model, then `cost_model` (Azure's real model),
   then extra ids (Bedrock `model_id` behind an ARN). First match wins and
   replaces provider defaults field by field. `inherit` takes another
   provider's resolved limits for the rest of the slug (OpenRouter).
3. The Anthropic 100-vs-600 split comes from our own 200k-model regex, not
   litellm's `max_input_tokens` (which is wrong for Sonnet 4.5).
4. Resolution never reads `litellm.model_cost`, so the remote and bundled
   cost maps resolve the same validated string identically. Only
   `local_max_input_tokens` reads the (local) registry.

## Checks (`policy.py`)

`compute_page_budget` = min(image count, (context − reserve) / tokens per
page, LLMWhisperer's 999, operator ceilings). `ImageModePolicy` adds the
raw-byte budget, per-image byte/pixel limits and the Anthropic ">20 images
⇒ ≤2000 px" rule; `check_page_set` applies them to a page set. Tunables are
module constants: `PROMPT_TOKENS_RESERVE`, `ENFORCE_CONTEXT_TOKEN_TERM`,
`ENFORCE_PER_IMAGE_LIMITS`, `TEXT_RESERVE_BYTES`, `ASSUMED_PAGE_BYTES`
(pre-conversion size advisory only, never a rejection) and
`PASS_THROUGH_DEFAULTS_ARE_ADVISORY` in `resolve.py`.

Operator ceilings: `VLM_IMAGE_ANSWER_PAGE_CAP` and
`VLM_IMAGE_ANSWER_MAX_TOTAL_MB` (MiB) are read by
`configured_page_ceiling()` / `configured_request_bytes_ceiling()` and only
ever tighten a model's limits.

## Patching without a release

`VLM_IMAGE_LIMITS_FILE=/path/to/override.json` names a file in the same
schema. A provider present in it replaces the shipped entry wholesale (no
deep merge); a `default` block replaces the default; `sources` are merged.
A malformed file is logged and ignored. This is the hook a future per-org
override would plug into (override → shipped → default).

## Maintaining the data

1. Change a number only with a source: add or update the `sources` entry
   (URL, quote, `verified_on`), set `confidence: verified` only when the
   page states the number for that scope.
2. Probe before trusting an `unverified` value: send N and N+1 images to
   the model; record the result in the note.
3. Keep overrides ordered specific → general (first match wins) and repeat
   every field that differs from the provider defaults.
4. Run `pytest tests/test_image_limits_*.py`: the table test rejects
   unknown keys, unresolved sources, bad regexes and missing providers.
5. The dataset's research and verification log live outside the repo
   (`claudedocs/vlm-consumer/model-limits/`); `_meta.source_dataset`
   points at them.
