#: The `kv` extractor's name -- the key-value/agentic-KV engine, routable
#: alongside `table` (see `EXTRACTOR_ROUTES` below).
#:
#: One API, one parameter: a caller picks the engine with `extractors[].name`,
#: `"kv"` or `"table"`. There is no separate KV endpoint and no second
#: selector; both run the same submit path, the same staging, the same
#: concurrency and page caps, and differ only in which executor the job
#: dispatches to and which `keys` grammar validates it.
#:
#: Two earlier versions of this comment are worth not reinstating. The first
#: said "v1 accepts exactly one extractor (`kv`), so the job row does not
#: carry which one it ran" -- `AgentKVJob.extractor` has carried the name since
#: migration 0002. The second said `kv` was "the one extractor this deployment
#: does NOT accept", which was true only while the engine was unshipped.
V1_EXTRACTOR_NAME = "kv"

STAGE_NAMES = [
    "document_processing",
    "extraction",
    "qa",
    "challenge",
    "normalize",
    "constraints",
    "codegen",
    "code_execution",
]
EXECUTOR_NAME = "agentic_kv"
OPERATION_KV_EXTRACT = "kv_extract"
EXECUTION_SOURCE = "agent_kv_api"

#: The table extractor, served by the cloud `agentic_table` plugin's blind-API
#: operation. Same executor as the IDE table path (and therefore the same,
#: already-wired `celery_executor_agentic_table` queue) with a second operation
#: -- a new executor name would derive a new queue needing wiring at five
#: sites, and an unwired queue accepts work and drains nothing, silently.
TABLE_EXTRACTOR_NAME = "table"

TABLE_EXECUTOR_NAME = "agentic_table"
OPERATION_TABLE_EXTRACT_API = "table_extract_api"

#: Which executor and operation each extractor dispatches to. `dispatch_job`
#: reads this rather than hardcoding one pair, so adding an extractor is one
#: entry here plus its options serializer, stage list and -- where the executor
#: requires adapters -- its adapters serializer, AND its entry in the
#: acceptance gate (`_EXTRACTOR_ENABLE_FLAGS` in `execution_serializers.py` --
#: a setting name to gate it, or `_UNGATED` to accept it everywhere, with
#: `test_every_routed_extractor_has_a_gate_entry` deriving the requirement from
#: this table so the step cannot be skipped). An earlier revision named this
#: step while the gate was a single `if` on one hard-coded name, so there was
#: nowhere to put the entry and a new extractor inherited the
#: 202-into-a-dead-queue shape this very comment warns about. `SUPPORTED_EXTRACTORS` is derived from
#: these keys (`execution_serializers.py`), so this table decides what is
#: ROUTED -- NOT what `extractors[].name` accepts, which is
#: `enabled_extractors()`'s. An earlier wording claimed "this table alone
#: decides what accepts", contradicting the paragraph two below it.
#:
#: **This table is where work GOES, not proof anything collects it.** The queue
#: is derived from the executor name, so an entry pointing at a plugin this
#: deployment does not ship is accepted with a 202, dispatched to a queue with
#: no consumer, and sits in DISPATCHED until the sweep force-fails it as
#: `FAILED "Job timed out"` (`maintenance.py` phase 2, after
#: `AGENT_KV_STUCK_JOB_GRACE_SECONDS`), releasing the slot and firing the
#: terminal webhook. NOT "forever": the row is terminalized, which matters
#: because an operator who reads "forever" goes looking for a stuck-row
#: cleanup that already ran, and reads the resulting `Job timed out` as a
#: different incident from the undrained queue. What is genuinely absent is any
#: error at the producer and anything in a log naming the cause.
#:
#: Routing `kv` is therefore NOT what enables it. Acceptance is gated separately,
#: on `AGENT_KV_KV_EXTRACTOR_ENABLED` (`enabled_extractors()` in
#: `execution_serializers.py`), which the chart sets in the same values file
#: that adds `celery_executor_agentic_kv` to the executor fleet's queue list.
#: The flag defaults false, which is what makes the merge order safe: this repo
#: merges first -- the cloud half imports `unstract-agent-kv-schema` from it --
#: and until the chart lands a `kv` submit is refused at validation instead of
#: being accepted into a queue nothing serves.
#:
#: An earlier revision of this comment listed three facts "checked against a
#: running deployment", the third citing `agent_kv_wiring_test.yaml::AKV-Q5b`
#: as pinning that the fleet subscribes. That citation was a FORWARD reference
#: and is worth recording as one: on the cloud repo's `main` that test asserts
#: the subscription is ABSENT ("the executor ConfigMap does not subscribe to
#: the agentic_kv queue"), and it is inverted only by the paired cloud PR. The
#: dev environment those facts were checked against was running both halves, so
#: the check was real but described no deployable image built from `main`. The
#: flag above replaces the convention that the two PRs would land together with
#: something a deployment states about itself.
#:
#: `EXECUTOR_NAME`/`OPERATION_KV_EXTRACT` matching what `AgenticKVExecutor`
#: dispatches on is still pinned by `test_the_kv_route_targets_the_shipped_executor`.
EXTRACTOR_ROUTES = {
    V1_EXTRACTOR_NAME: (EXECUTOR_NAME, OPERATION_KV_EXTRACT),
    TABLE_EXTRACTOR_NAME: (TABLE_EXECUTOR_NAME, OPERATION_TABLE_EXTRACT_API),
}

#: The table engine reports one coarse stage: it has no node-level progress
#: hooks (the IDE path gets `stream_log` only), so inventing finer stages here
#: would describe progress the executor cannot actually report.
TABLE_STAGE_NAMES = ["table_extraction"]

#: Stage names ARE wire format -- they are returned to clients -- and they are
#: extractor-specific (`qa`/`challenge`/`codegen` mean nothing to the table
#: extractor). `_status_document` filters a job's recorded stages through the
#: list for the extractor that ran: `StageReportView` persists whatever name
#: the executor sends, so without a per-extractor list a table job's stages
#: would be stored and then silently filtered out of every status response.
STAGE_NAMES_BY_EXTRACTOR = {
    V1_EXTRACTOR_NAME: STAGE_NAMES,
    TABLE_EXTRACTOR_NAME: TABLE_STAGE_NAMES,
}


#: The x2text adapter that can produce highlight and confidence data, by the
#: provider descriptor `AdapterInstance.adapter_id` carries.
#:
#: A literal rather than an import: pulling the SDK adapter class into a
#: request path to read one `get_id()` drags its whole registry in. The literal
#: is pinned to the SDK's own value by
#: `tests/test_highlight_gate.py::test_the_whisperer_id_matches_the_sdk`, so it
#: cannot drift silently.
#:
#: **V2 only, and that is the point.** Only `llm_whisperer_v2`'s helper fetches
#: `line_metadata` -- `enable_highlight` there sets both `ADD_LINE_NOS` and
#: `INCLUDE_LINE_CONFIDENCE` and then calls `get_highlight_data`
#: (`sdk1/.../x2text/llm_whisperer_v2/src/helper.py`). No other x2text adapter
#: has that path, so highlight on any of them would return an empty block the
#: caller paid for.
LLM_WHISPERER_ADAPTER_ID = "llmwhisperer|a5e6b8af-3e1f-4a80-b006-d017e8e67f93"

#: `hitl_queue_name`'s accepted shape, matching the documented API-deployment
#: field it mirrors (docs: "Push to HITL from API Deployments"): alphanumerics,
#: hyphens and underscores, and short enough to stay readable in a queue name.
#:
#: The queue this ends up addressing is
#: `review_queue_{organization_id}_{class}:{hitl_queue_name}`, so a name
#: carrying `:` or whitespace would alter the queue's own structure rather than
#: name a queue within it. That is why this is a refusal and not a sanitiser.
HITL_QUEUE_NAME_RE = r"^[A-Za-z0-9_-]{1,50}$"

#: The `class` slot of that queue name. The API-deployment path puts a workflow
#: id there; this API has no workflow, so the whole API is one namespace and
#: the caller's `hitl_queue_name` subdivides it -- exactly how a workflow's
#: queue is subdivided today.
HITL_QUEUE_CLASS = "agentic-extract"

#: `queue_type` for records pushed over an API rather than drained from an ETL
#: pipeline. `HITLQueue.queue_type` already carries this value for the
#: API-deployment path; its `workflow` FK is nullable for the same reason.
HITL_QUEUE_TYPE_API = "api"
