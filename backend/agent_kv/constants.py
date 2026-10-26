#: The `kv` extractor's name. Kept as a constant, but NOT routable on this
#: deployment -- see `EXTRACTOR_ROUTES` below, which carries `table` only.
#:
#: An earlier version of this comment said "v1 accepts exactly one extractor
#: (`kv`), so the job row does not carry which one it ran". Both halves are now
#: wrong, on line 1 of the file that defines the routing table: `kv` is the one
#: extractor this deployment does NOT accept, and `AgentKVJob.extractor` has
#: carried the name since migration 0002.
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
#: entry here plus its options serializer and stage list.
#:
#: **`kv` is deliberately absent.** This deployment ships the `agentic_table`
#: plugin and not `agentic_kv`, so nothing drains `celery_executor_agentic_kv`.
#: `SUPPORTED_EXTRACTORS` is derived from this table's keys
#: (`execution_serializers.py`), so the omission turns a `kv` submit into a 400
#: at the serializer. Restoring the entry below is all it takes to re-enable
#: the extractor once the plugin ships -- and restoring it WITHOUT the plugin
#: is the failure this guards: the submit would be accepted with a 202,
#: dispatched to a queue with no consumer, and sit in DISPATCHED forever with
#: no error at the producer and nothing in any log to find.
#:
#: `V1_EXTRACTOR_NAME`, `STAGE_NAMES` and the KV options serializer stay in the
#: tree, dormant and still under test, so re-enabling is one line rather than a
#: content merge against the branch that carries the engine.
EXTRACTOR_ROUTES = {
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
