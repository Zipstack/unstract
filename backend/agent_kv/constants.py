#: v1 accepts exactly one extractor (`kv`), so the job row does not carry which
#: one it ran. When fan-out lands this becomes per-job state rather than a
#: constant -- the wire format (spec §7.0) is already shaped for that.
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
