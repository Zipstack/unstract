"""Structure tool Celery task — Phase 3 of executor migration.

Replaces the Docker-container-based StructureTool.run() with a Celery
task that runs in the file_processing worker. Instead of PromptTool
HTTP calls to prompt-service, it uses ExecutionDispatcher to send
operations to the executor worker via Celery.

Before (Docker-based):
    File Processing Worker → WorkflowExecutionService → ToolSandbox
    → Docker container → StructureTool.run() → PromptTool (HTTP) → prompt-service

After (Celery-based):
    File Processing Worker → WorkerWorkflowExecutionService
    → execute_structure_tool task → ExecutionDispatcher
    → executor worker → LegacyExecutor
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from file_processing.worker import app
from shared.enums.task_enums import TaskName
from shared.infrastructure.context import StateStore

from unstract.sdk1.constants import ToolEnv, UsageKwargs
from unstract.sdk1.execution.context import ExecutionContext
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher
from unstract.sdk1.execution.result import ExecutionResult

logger = logging.getLogger(__name__)

# Timeout for executor worker calls (seconds).
# Reads from EXECUTOR_RESULT_TIMEOUT env, defaults to 3600.
EXECUTOR_TIMEOUT = int(os.environ.get("EXECUTOR_RESULT_TIMEOUT", 3600))


# -----------------------------------------------------------------------
# Constants mirrored from tools/structure/src/constants.py
# These are the keys used in tool_metadata and payload dicts.
# -----------------------------------------------------------------------


class _SK:
    """SettingsKeys subset needed by the structure tool task."""

    PROMPT_REGISTRY_ID = "prompt_registry_id"
    TOOL_METADATA = "tool_metadata"
    TOOL_ID = "tool_id"
    OUTPUTS = "outputs"
    TOOL_SETTINGS = "tool_settings"
    NAME = "name"
    ACTIVE = "active"
    PROMPT = "prompt"
    CHUNK_SIZE = "chunk-size"
    CHUNK_OVERLAP = "chunk-overlap"
    VECTOR_DB = "vector-db"
    EMBEDDING = "embedding"
    X2TEXT_ADAPTER = "x2text_adapter"
    LLM = "llm"
    CHALLENGE_LLM = "challenge_llm"
    ENABLE_CHALLENGE = "enable_challenge"
    ENABLE_SINGLE_PASS_EXTRACTION = "enable_single_pass_extraction"
    SUMMARIZE_AS_SOURCE = "summarize_as_source"
    ENABLE_HIGHLIGHT = "enable_highlight"
    ENABLE_WORD_CONFIDENCE = "enable_word_confidence"
    SUMMARIZE_PROMPT = "summarize_prompt"
    TABLE_SETTINGS = "table_settings"
    INPUT_FILE = "input_file"
    IS_DIRECTORY_MODE = "is_directory_mode"
    RUN_ID = "run_id"
    EXECUTION_ID = "execution_id"
    FILE_HASH = "file_hash"
    FILE_NAME = "file_name"
    FILE_PATH = "file_path"
    EXECUTION_SOURCE = "execution_source"
    TOOL = "tool"
    EXTRACT = "EXTRACT"
    SUMMARIZE = "SUMMARIZE"
    METADATA = "metadata"
    METRICS = "metrics"
    INDEXING = "indexing"
    OUTPUT = "output"
    CONTEXT = "context"
    DATA = "data"
    LLM_ADAPTER_INSTANCE_ID = "llm_adapter_instance_id"
    PROMPT_KEYS = "prompt_keys"
    LLM_PROFILE_ID = "llm_profile_id"
    CUSTOM_DATA = "custom_data"
    SINGLE_PASS_EXTRACTION_MODE = "single_pass_extraction_mode"
    CHALLENGE_LLM_ADAPTER_ID = "challenge_llm_adapter_id"


# -----------------------------------------------------------------------
# Standalone helper functions (extracted from StructureTool methods)
# -----------------------------------------------------------------------


def _apply_profile_overrides(tool_metadata: dict, profile_data: dict) -> list[str]:
    """Apply profile overrides to tool metadata.

    Standalone version of StructureTool._apply_profile_overrides.
    """
    changes: list[str] = []

    profile_to_tool_mapping = {
        "chunk_overlap": "chunk-overlap",
        "chunk_size": "chunk-size",
        "embedding_model_id": "embedding",
        "llm_id": "llm",
        "similarity_top_k": "similarity-top-k",
        "vector_store_id": "vector-db",
        "x2text_id": "x2text_adapter",
        "retrieval_strategy": "retrieval-strategy",
    }

    if "tool_settings" in tool_metadata:
        changes.extend(
            _override_section(
                tool_metadata["tool_settings"],
                profile_data,
                profile_to_tool_mapping,
                "tool_settings",
            )
        )

    if "outputs" in tool_metadata:
        for i, output in enumerate(tool_metadata["outputs"]):
            output_name = output.get("name", f"output_{i}")
            changes.extend(
                _override_section(
                    output,
                    profile_data,
                    profile_to_tool_mapping,
                    f"output[{output_name}]",
                )
            )

    return changes


def _override_section(
    section: dict,
    profile_data: dict,
    mapping: dict,
    section_name: str = "section",
) -> list[str]:
    """Override values in a section using profile data."""
    changes: list[str] = []
    for profile_key, section_key in mapping.items():
        if profile_key in profile_data and section_key in section:
            old_value = section[section_key]
            new_value = profile_data[profile_key]
            if old_value != new_value:
                section[section_key] = new_value
                change_desc = f"{section_name}.{section_key}: {old_value} -> {new_value}"
                changes.append(change_desc)
                logger.info("Overrode %s", change_desc)
    return changes


def _should_skip_extraction_for_smart_table(
    outputs: list[dict[str, Any]],
) -> bool:
    """Check if extraction and indexing should be skipped for smart table.

    Standalone version of StructureTool._should_skip_extraction_for_smart_table.
    """
    for output in outputs:
        if _SK.TABLE_SETTINGS not in output:
            continue
        prompt = output.get(_SK.PROMPT, "")
        if not prompt or not isinstance(prompt, str):
            continue
        try:
            schema_data = json.loads(prompt)
        except ValueError as e:
            logger.warning("Failed to parse prompt as JSON for smart table: %s", e)
            continue
        if isinstance(schema_data, dict) and schema_data:
            return True
    return False


# -----------------------------------------------------------------------
# Main Celery task
# -----------------------------------------------------------------------


@app.task(bind=True, name=str(TaskName.EXECUTE_STRUCTURE_TOOL))
def execute_structure_tool(self, params: dict) -> dict:
    """Execute structure tool as a Celery task.

    Replicates StructureTool.run() from tools/structure/src/main.py
    but uses ExecutionDispatcher instead of PromptTool HTTP calls.

    Args:
        params: Dict with keys described in the Phase 3 plan.

    Returns:
        Dict with {"success": bool, "data": dict, "error": str|None}.
    """
    try:
        return _execute_structure_tool_impl(params)
    except Exception as e:
        logger.error("Structure tool task failed: %s", e, exc_info=True)
        return ExecutionResult.failure(error=f"Structure tool failed: {e}").to_dict()


def _execute_structure_tool_impl(params: dict) -> dict:
    """Implementation of the structure tool pipeline.

    Separated from the task function for testability.

    Phase 5E: Uses a single ``structure_pipeline`` dispatch instead of
    3 sequential ``dispatcher.dispatch()`` calls.  The executor worker
    handles the full extract → summarize → index → answer_prompt
    pipeline internally, freeing the file_processing worker slot.
    """
    # ---- Unpack params ----
    organization_id = params["organization_id"]
    execution_id = params.get("execution_id", "")
    file_execution_id = params["file_execution_id"]
    tool_instance_metadata = params["tool_instance_metadata"]
    platform_service_api_key = params["platform_service_api_key"]
    input_file_path = params["input_file_path"]
    output_dir_path = params["output_dir_path"]
    source_file_name = params["source_file_name"]
    execution_data_dir = params["execution_data_dir"]
    file_hash = params.get("file_hash", "")
    exec_metadata = params.get("exec_metadata", {})

    # ---- Step 1: Setup ----
    from executor.executor_tool_shim import ExecutorToolShim

    # Workflow IDs on the pre-dispatch shim let X2Text/platform helper logs
    # reach the workflow logs UI before the executor dispatch happens.
    log_events_id = StateStore.get("LOG_EVENTS_ID") or ""
    if not log_events_id:
        logger.warning(
            "LOG_EVENTS_ID missing from StateStore for execution_id=%s — "
            "tool-level logs will not stream to the workflow logs UI.",
            execution_id,
        )
    shim = ExecutorToolShim(
        platform_api_key=platform_service_api_key,
        log_events_id=log_events_id,
        execution_id=execution_id,
        file_execution_id=file_execution_id,
        organization_id=organization_id,
    )

    platform_helper = _create_platform_helper(shim, file_execution_id)
    dispatcher = ExecutionDispatcher(celery_app=app)
    fs = _get_file_storage()

    # ---- Step 2: Fetch tool metadata ----
    prompt_registry_id = tool_instance_metadata.get(_SK.PROMPT_REGISTRY_ID, "")
    logger.info("Fetching exported tool with UUID '%s'", prompt_registry_id)

    tool_metadata, is_agentic = _fetch_tool_metadata(platform_helper, prompt_registry_id)

    # ---- Route agentic vs regular ----
    if is_agentic:
        return _run_agentic_extraction(
            tool_metadata=tool_metadata,
            input_file_path=input_file_path,
            output_dir_path=output_dir_path,
            tool_instance_metadata=tool_instance_metadata,
            dispatcher=dispatcher,
            shim=shim,
            file_execution_id=file_execution_id,
            execution_id=execution_id,
            organization_id=organization_id,
            source_file_name=source_file_name,
            fs=fs,
            execution_data_dir=execution_data_dir,
        )

    # ---- Step 3: Profile overrides ----
    _handle_profile_overrides(exec_metadata, platform_helper, tool_metadata)

    # ---- Extract settings from tool_metadata ----
    settings = tool_instance_metadata
    is_challenge_enabled = settings.get(_SK.ENABLE_CHALLENGE, False)
    is_summarization_enabled = settings.get(_SK.SUMMARIZE_AS_SOURCE, False)
    is_single_pass_enabled = settings.get(_SK.SINGLE_PASS_EXTRACTION_MODE, False)
    challenge_llm = settings.get(_SK.CHALLENGE_LLM_ADAPTER_ID, "")
    is_highlight_enabled = settings.get(_SK.ENABLE_HIGHLIGHT, False)
    is_word_confidence_enabled = settings.get(_SK.ENABLE_WORD_CONFIDENCE, False)
    logger.info(
        "HIGHLIGHT_DEBUG structure_tool: is_highlight_enabled=%s "
        "is_word_confidence_enabled=%s from settings keys=%s",
        is_highlight_enabled,
        is_word_confidence_enabled,
        list(settings.keys()),
    )

    tool_id = tool_metadata[_SK.TOOL_ID]
    tool_settings = tool_metadata[_SK.TOOL_SETTINGS]
    all_outputs = tool_metadata[_SK.OUTPUTS]

    # ---- Partition prompts by enforce_type ----
    # Agentic table prompts run via a dedicated executor (page-by-page
    # extraction + Agent-5 schema cleanup). Regular prompts continue
    # through the legacy structure_pipeline. Use local variables so
    # tool_metadata[_SK.OUTPUTS] is preserved for METADATA.json
    # serialization downstream in _write_tool_result.
    agentic_table_outputs = [o for o in all_outputs if o.get("type") == "agentic_table"]
    regular_outputs = [o for o in all_outputs if o.get("type") != "agentic_table"]

    # Validate readiness for each agentic_table prompt: if the export
    # step did not populate agentic_table_settings, fail loudly so the
    # user knows to re-export the tool instead of producing the
    # legacy stringified-truncated output.
    for at_output in agentic_table_outputs:
        at_settings = at_output.get("agentic_table_settings") or {}
        if not at_settings.get("target_table") or not at_settings.get("json_structure"):
            return ExecutionResult.failure(
                error=(
                    f"Agentic table prompt '{at_output[_SK.NAME]}' is missing "
                    f"agentic_table_settings in the exported tool metadata. "
                    f"Re-export the tool from Prompt Studio after the fix is "
                    f"deployed to populate target_table / json_structure / "
                    f"instructions."
                )
            ).to_dict()

    outputs = regular_outputs

    # Inject workflow-level settings into tool_settings
    tool_settings[_SK.CHALLENGE_LLM] = challenge_llm
    tool_settings[_SK.ENABLE_CHALLENGE] = is_challenge_enabled
    tool_settings[_SK.ENABLE_SINGLE_PASS_EXTRACTION] = is_single_pass_enabled
    tool_settings[_SK.SUMMARIZE_AS_SOURCE] = is_summarization_enabled
    tool_settings[_SK.ENABLE_HIGHLIGHT] = is_highlight_enabled
    tool_settings[_SK.ENABLE_WORD_CONFIDENCE] = is_word_confidence_enabled

    _, file_name = os.path.split(input_file_path)
    if is_summarization_enabled:
        file_name = _SK.SUMMARIZE

    execution_run_data_folder = Path(execution_data_dir)
    extracted_input_file = str(execution_run_data_folder / _SK.EXTRACT)

    # ---- Step 4: Smart table detection ----
    skip_extraction_and_indexing = _should_skip_extraction_for_smart_table(outputs)
    if skip_extraction_and_indexing:
        logger.info(
            "Skipping extraction and indexing for Excel table with valid JSON schema"
        )

    # ---- Step 5: Build pipeline params ----
    usage_kwargs: dict[Any, Any] = {}
    if not skip_extraction_and_indexing:
        usage_kwargs[UsageKwargs.RUN_ID] = file_execution_id
        usage_kwargs[UsageKwargs.FILE_NAME] = source_file_name
        usage_kwargs[UsageKwargs.EXECUTION_ID] = execution_id

    custom_data = exec_metadata.get(_SK.CUSTOM_DATA, {})
    answer_params = {
        _SK.RUN_ID: file_execution_id,
        _SK.EXECUTION_ID: execution_id,
        _SK.TOOL_SETTINGS: tool_settings,
        _SK.OUTPUTS: outputs,
        _SK.TOOL_ID: tool_id,
        _SK.FILE_HASH: file_hash,
        _SK.FILE_NAME: file_name,
        _SK.FILE_PATH: extracted_input_file,
        _SK.EXECUTION_SOURCE: _SK.TOOL,
        _SK.CUSTOM_DATA: custom_data,
        "PLATFORM_SERVICE_API_KEY": platform_service_api_key,
    }

    extract_params = {
        "x2text_instance_id": tool_settings[_SK.X2TEXT_ADAPTER],
        "file_path": input_file_path,
        "enable_highlight": is_highlight_enabled,
        "output_file_path": str(execution_run_data_folder / _SK.EXTRACT),
        "platform_api_key": platform_service_api_key,
        "usage_kwargs": usage_kwargs,
        "tags": exec_metadata.get("tags"),
        "tool_execution_metadata": exec_metadata,
        "execution_data_dir": str(execution_run_data_folder),
    }

    index_template = {
        "tool_id": tool_id,
        "file_hash": file_hash,
        "is_highlight_enabled": is_highlight_enabled,
        "platform_api_key": platform_service_api_key,
        "extracted_file_path": extracted_input_file,
    }

    pipeline_options = {
        "skip_extraction_and_indexing": skip_extraction_and_indexing,
        "is_summarization_enabled": is_summarization_enabled,
        "is_single_pass_enabled": is_single_pass_enabled,
        "input_file_path": input_file_path,
        "source_file_name": source_file_name,
    }

    # Build summarize params if enabled
    summarize_params = None
    if is_summarization_enabled:
        prompt_keys = [o[_SK.NAME] for o in outputs]
        summarize_params = {
            "llm_adapter_instance_id": tool_settings[_SK.LLM],
            "summarize_prompt": tool_settings.get(_SK.SUMMARIZE_PROMPT, ""),
            "extract_file_path": str(execution_run_data_folder / _SK.EXTRACT),
            "summarize_file_path": str(execution_run_data_folder / _SK.SUMMARIZE),
            "platform_api_key": platform_service_api_key,
            "prompt_keys": prompt_keys,
        }

    # ---- Step 6a: Dispatch agentic_table prompts ----
    # Each agentic_table prompt runs in its own executor invocation.
    # The executor handles X2Text extraction internally; we just
    # forward the document path and the per-prompt settings unpacked
    # from agentic_table_settings (populated by Layer 1 export).
    #
    # Important: read from SOURCE, not INFILE. INFILE gets overwritten
    # with JSON output at the end of this function (line ~508), so any
    # subsequent reuse of the same file_execution_dir would surface JSON
    # bytes to the agentic_table executor and fail PDF parsing
    # ("PDFium: Data format error"). SOURCE is the immutable original
    # PDF written alongside INFILE by the source connector.
    agentic_source_path = str(execution_run_data_folder / "SOURCE")
    agentic_results: dict[str, Any] = {}
    for at_output in agentic_table_outputs:
        at_settings = at_output.get("agentic_table_settings") or {}
        json_structure = at_settings.get("json_structure")
        if isinstance(json_structure, dict):
            json_structure = json.dumps(json_structure)
        agentic_params = {
            "llm_adapter_instance_id": at_output["llm"],
            "lite_llm_adapter_instance_id": at_settings.get(
                "lite_llm_adapter_instance_id", ""
            ),
            "x2text_adapter_instance_id": tool_settings[_SK.X2TEXT_ADAPTER],
            "input_file": agentic_source_path,
            "source_file_name": source_file_name,
            "target_table": at_settings.get("target_table", ""),
            "json_structure": json_structure,
            "instructions": at_settings.get("instructions", ""),
            "starting_page": at_settings.get("start_page", 1),
            "ending_page": at_settings.get("end_page") or None,
            "parallel_pages": at_settings.get("parallel_pages", 4),
            "execution_id": execution_id,
            "PLATFORM_SERVICE_API_KEY": platform_service_api_key,
        }
        at_ctx = ExecutionContext(
            executor_name="agentic_table",
            operation="table_extract",
            run_id=file_execution_id,
            execution_source="tool",
            organization_id=organization_id,
            request_id=file_execution_id,
            log_events_id=log_events_id,
            execution_id=execution_id,
            file_execution_id=file_execution_id,
            executor_params=agentic_params,
        )
        at_result = dispatcher.dispatch(at_ctx, timeout=EXECUTOR_TIMEOUT)
        if not at_result.success:
            return at_result.to_dict()
        at_output_data = at_result.data.get("output", {}) or {}
        agentic_results[at_output[_SK.NAME]] = at_output_data.get("tables", [])

    # ---- Step 6b: Dispatch legacy structure_pipeline ----
    # Skipped entirely when every prompt is agentic_table — the legacy
    # pipeline has no work to do and the agentic_table executor does
    # its own X2Text inside the runner.
    if regular_outputs:
        logger.info(
            "Dispatching structure_pipeline: tool_id=%s "
            "skip_extract=%s summarize=%s single_pass=%s",
            tool_id,
            skip_extraction_and_indexing,
            is_summarization_enabled,
            is_single_pass_enabled,
        )

        pipeline_ctx = ExecutionContext(
            executor_name="legacy",
            operation="structure_pipeline",
            run_id=file_execution_id,
            execution_source="tool",
            organization_id=organization_id,
            request_id=file_execution_id,
            log_events_id=log_events_id,
            execution_id=execution_id,
            file_execution_id=file_execution_id,
            executor_params={
                "extract_params": extract_params,
                "index_template": index_template,
                "answer_params": answer_params,
                "pipeline_options": pipeline_options,
                "summarize_params": summarize_params,
            },
        )
        pipeline_start = time.monotonic()
        pipeline_result = dispatcher.dispatch(pipeline_ctx, timeout=EXECUTOR_TIMEOUT)
        pipeline_elapsed = time.monotonic() - pipeline_start

        if not pipeline_result.success:
            return pipeline_result.to_dict()

        structured_output = pipeline_result.data
        if agentic_results:
            structured_output.setdefault("output", {}).update(agentic_results)
    else:
        # All-agentic case: skip the legacy pipeline entirely.
        structured_output = {
            "output": agentic_results,
            "metadata": {"agentic_only": True},
        }
        pipeline_elapsed = 0.0

    # ---- Step 7: Write output files ----
    # (metadata/metrics merging already done by executor pipeline)
    write_error = _write_pipeline_outputs(
        fs=fs,
        structured_output=structured_output,
        output_dir_path=output_dir_path,
        input_file_path=input_file_path,
        execution_data_dir=execution_data_dir,
        source_file_name=source_file_name,
        label="structured",
    )
    if write_error:
        return ExecutionResult.failure(
            error=f"Error writing output file: {write_error}"
        ).to_dict()

    # Write tool result + tool_metadata to METADATA.json
    # (destination connector reads output_type from tool_metadata)
    _write_tool_result(fs, execution_data_dir, structured_output, pipeline_elapsed)

    return ExecutionResult(success=True, data=structured_output).to_dict()


# -----------------------------------------------------------------------
# Helper functions for the pipeline steps
# -----------------------------------------------------------------------


def _create_platform_helper(shim, request_id: str):
    """Create PlatformHelper using env vars for host/port."""
    from unstract.sdk1.platform import PlatformHelper

    return PlatformHelper(
        tool=shim,
        platform_host=os.environ.get(ToolEnv.PLATFORM_HOST, ""),
        platform_port=os.environ.get(ToolEnv.PLATFORM_PORT, ""),
        request_id=request_id,
    )


def _get_file_storage():
    """Get workflow execution file storage instance."""
    from unstract.filesystem import FileStorageType, FileSystem

    return FileSystem(FileStorageType.WORKFLOW_EXECUTION).get_file_storage()


def _fetch_tool_metadata(platform_helper, prompt_registry_id: str) -> tuple[dict, bool]:
    """Fetch tool metadata from platform, trying prompt studio then agentic.

    Returns:
        Tuple of (tool_metadata dict, is_agentic bool).

    Raises:
        RuntimeError: If neither registry returns valid metadata.
    """
    exported_tool = None
    try:
        exported_tool = platform_helper.get_prompt_studio_tool(
            prompt_registry_id=prompt_registry_id
        )
    except Exception as e:
        logger.info("Not found as prompt studio project, trying agentic: %s", e)

    if exported_tool and _SK.TOOL_METADATA in exported_tool:
        tool_metadata = exported_tool[_SK.TOOL_METADATA]
        tool_metadata["is_agentic"] = False
        return tool_metadata, False

    # Try agentic registry
    try:
        agentic_tool = platform_helper.get_agentic_studio_tool(
            agentic_registry_id=prompt_registry_id
        )
        if not agentic_tool or _SK.TOOL_METADATA not in agentic_tool:
            raise RuntimeError(
                f"Registry returned empty response for {prompt_registry_id}"
            )
        tool_metadata = agentic_tool[_SK.TOOL_METADATA]
        tool_metadata["is_agentic"] = True
        logger.info(
            "Retrieved agentic project: %s",
            tool_metadata.get("name", prompt_registry_id),
        )
        return tool_metadata, True
    except Exception as agentic_error:
        raise RuntimeError(
            f"Error fetching project from both registries "
            f"for ID '{prompt_registry_id}': {agentic_error}"
        ) from agentic_error


def _handle_profile_overrides(
    exec_metadata: dict, platform_helper, tool_metadata: dict
) -> None:
    """Apply LLM profile overrides if configured."""
    llm_profile_id = exec_metadata.get(_SK.LLM_PROFILE_ID)
    if not llm_profile_id:
        return

    try:
        llm_profile = platform_helper.get_llm_profile(llm_profile_id)
        if llm_profile:
            profile_name = llm_profile.get("profile_name", llm_profile_id)
            logger.info(
                "Applying profile overrides from profile: %s",
                profile_name,
            )
            changes = _apply_profile_overrides(tool_metadata, llm_profile)
            if changes:
                logger.info(
                    "Profile overrides applied. Changes: %s",
                    "; ".join(changes),
                )
            else:
                logger.info("Profile overrides applied - no changes needed")
    except Exception as e:
        raise RuntimeError(f"Error applying profile overrides: {e}") from e


def _run_agentic_extraction(
    tool_metadata: dict,
    input_file_path: str,
    output_dir_path: str,
    tool_instance_metadata: dict,
    dispatcher: ExecutionDispatcher,
    shim: Any,
    file_execution_id: str,
    execution_id: str,
    organization_id: str,
    source_file_name: str,
    fs: Any,
    execution_data_dir: str = "",
) -> dict:
    """Execute agentic extraction pipeline via dispatcher.

    Unpacks metadata, extracts document text via X2Text, then dispatches
    with flat executor_params matching what AgenticPromptStudioExecutor
    expects (adapter_instance_id, document_text, etc.).
    """
    from unstract.sdk1.x2txt import X2Text

    # 1. Unpack agentic project metadata (matches registry_helper export format)
    adapter_config = tool_metadata.get("adapter_config", {})
    prompt_text = tool_metadata.get("prompt_text", "")
    json_schema = tool_metadata.get("json_schema", {})
    enable_highlight = tool_instance_metadata.get(
        "enable_highlight",
        tool_metadata.get("enable_highlight", False),
    )

    # 2. Get adapter IDs: workflow UI overrides → exported defaults
    #    (mirrors tools/structure/src/main.py)
    extractor_llm = tool_instance_metadata.get(
        "extractor_llm_adapter_id", adapter_config.get("extractor_llm", "")
    )
    llmwhisperer = tool_instance_metadata.get(
        "llmwhisperer_adapter_id", adapter_config.get("llmwhisperer", "")
    )
    platform_service_api_key = shim.platform_api_key

    # 3. Extract text from document using X2Text/LLMWhisperer
    x2text = X2Text(tool=shim, adapter_instance_id=llmwhisperer)
    extraction_result = x2text.process(
        input_file_path=input_file_path,
        enable_highlight=enable_highlight,
        fs=fs,
    )
    document_text = extraction_result.extracted_text

    # Parse json_schema if stored as string
    if isinstance(json_schema, str):
        json_schema = json.loads(json_schema)

    # 4. Dispatch with flat executor_params matching executor expectations
    start_time = time.monotonic()
    agentic_ctx = ExecutionContext(
        executor_name="agentic",
        operation="agentic_extract",
        run_id=file_execution_id,
        execution_source="tool",
        organization_id=organization_id,
        request_id=file_execution_id,
        log_events_id=StateStore.get("LOG_EVENTS_ID") or "",
        execution_id=execution_id,
        file_execution_id=file_execution_id,
        executor_params={
            "document_id": file_execution_id,
            "document_text": document_text,
            "prompt_text": prompt_text,
            "schema": json_schema,
            "adapter_instance_id": extractor_llm,
            "PLATFORM_SERVICE_API_KEY": platform_service_api_key,
            "include_source_refs": enable_highlight,
        },
    )
    agentic_result = dispatcher.dispatch(agentic_ctx, timeout=EXECUTOR_TIMEOUT)

    if not agentic_result.success:
        return agentic_result.to_dict()

    structured_output = agentic_result.data
    elapsed = time.monotonic() - start_time

    # Write output files (matches regular pipeline path)
    write_error = _write_pipeline_outputs(
        fs=fs,
        structured_output=structured_output,
        output_dir_path=output_dir_path,
        input_file_path=input_file_path,
        execution_data_dir=execution_data_dir,
        source_file_name=source_file_name,
        label="agentic",
    )
    if write_error:
        return ExecutionResult.failure(
            error=f"Error writing agentic output: {write_error}"
        ).to_dict()

    # Write tool result + tool_metadata to METADATA.json
    _write_tool_result(fs, execution_data_dir, structured_output, elapsed)

    return ExecutionResult(success=True, data=structured_output).to_dict()


def _write_pipeline_outputs(
    fs: Any,
    structured_output: dict,
    output_dir_path: str,
    input_file_path: str,
    execution_data_dir: str,
    source_file_name: str,
    label: str,
) -> str | None:
    """Write structure-tool / agentic outputs to disk.

    Mirrors the old Docker tool's output layout so the destination
    connector finds what it expects:

    1. ``{output_dir_path}/{stem}.json`` — primary output file.
    2. INFILE overwritten with JSON (destination connector reads INFILE
       and checks MIME type — without this it still sees the original
       PDF).
    3. ``{execution_data_dir}/COPY_TO_FOLDER/{stem}.json`` — what the
       old ``ToolExecutor._setup_for_run()`` created for FS destinations.

    Args:
        label: Short label for log lines (``"structured"`` or
            ``"agentic"``).

    Returns:
        ``None`` on success, or the error string on failure.
    """
    try:
        stem = Path(source_file_name).stem
        output_path = Path(output_dir_path) / f"{stem}.json"
        logger.info("Writing %s output to %s", label, output_path)
        fs.json_dump(path=output_path, data=structured_output)

        logger.info("Overwriting INFILE with %s output: %s", label, input_file_path)
        fs.json_dump(path=input_file_path, data=structured_output)

        copy_to_folder = str(Path(execution_data_dir) / "COPY_TO_FOLDER")
        fs.mkdir(copy_to_folder)
        copy_output_path = str(Path(copy_to_folder) / f"{stem}.json")
        fs.json_dump(path=copy_output_path, data=structured_output)
        logger.info(
            "%s output written to COPY_TO_FOLDER: %s",
            label.capitalize(),
            copy_output_path,
        )

        logger.info("Output written successfully to workflow storage")
        return None
    except Exception as e:
        logger.error("Failed to write %s output files: %s", label, e, exc_info=True)
        return str(e)


def _write_tool_result(
    fs: Any, execution_data_dir: str, _data: dict, elapsed_time: float = 0.0
) -> None:
    """Write tool result and tool_metadata to METADATA.json.

    Matches BaseTool._update_exec_metadata():
    - tool_metadata: list of dicts with tool_name, output_type, elapsed_time
      (destination connector reads output_type from here)
    - total_elapsed_time: cumulative elapsed time
    """
    metadata_path: Path | None = None
    try:
        metadata_path = Path(execution_data_dir) / "METADATA.json"

        # Read existing metadata if present
        existing: dict = {}
        if fs.exists(metadata_path):
            try:
                existing_raw = fs.read(path=metadata_path, mode="r")
                if existing_raw:
                    existing = json.loads(existing_raw)
            except Exception:
                pass

        # Add tool_metadata (matches BaseTool._update_exec_metadata)
        # The destination connector reads output_type from tool_metadata[-1]
        tool_meta_entry = {
            "tool_name": "structure_tool",
            "output_type": "JSON",
            "elapsed_time": elapsed_time,
        }
        if "tool_metadata" not in existing:
            existing["tool_metadata"] = [tool_meta_entry]
        else:
            existing["tool_metadata"].append(tool_meta_entry)

        existing["total_elapsed_time"] = (
            existing.get("total_elapsed_time", 0.0) + elapsed_time
        )

        fs.write(
            path=metadata_path,
            mode="w",
            data=json.dumps(existing, indent=2),
        )
    except Exception as e:
        logger.error(
            "Failed to write tool result to METADATA.json at '%s': %s",
            metadata_path,
            e,
            exc_info=True,
        )
