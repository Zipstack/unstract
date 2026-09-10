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
