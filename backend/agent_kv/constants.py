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
#: requires adapters -- its adapters serializer. `SUPPORTED_EXTRACTORS` is
#: derived from these keys (`execution_serializers.py`), so this table alone
#: decides what `extractors[].name` accepts.
#:
#: **Before adding an entry, confirm something drains the queue it names.** The
#: queue is derived from the executor name, so an entry pointing at a plugin
#: this deployment does not ship is accepted with a 202, dispatched to a queue
#: with no consumer, and sits in DISPATCHED forever -- no error at the
#: producer, nothing in any log to find. That is why `kv` was absent here: the
#: engine shipped on its own branch. It is present now, and the three facts
#: that make it safe were checked against a running deployment rather than
#: assumed:
#:
#:   1. the worker image carries the plugin (`agentic_kv.executor` imports);
#:   2. it registers this exact pair -- `EXECUTOR_NAME` == "agentic_kv" and
#:      `OPERATION_KV_EXTRACT` == "kv_extract", which `AgenticKVExecutor`
#:      dispatches on (`executor.py`, `context.operation != OPERATION_KV_EXTRACT`);
#:   3. the executor fleet subscribes to `celery_executor_agentic_kv`
#:      (`WORKER_PG_QUEUE_CONSUMER_QUEUE`, pinned chart-side by
#:      `agent_kv_wiring_test.yaml::AKV-Q5b`).
#:
#: Re-check 1 and 3 before enabling `kv` in an environment that has not run it;
#: 2 is pinned by `test_the_kv_route_targets_the_shipped_executor`.
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
