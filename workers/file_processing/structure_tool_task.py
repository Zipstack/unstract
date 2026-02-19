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
from pathlib import Path
from typing import Any

from file_processing.worker import app
from shared.enums.task_enums import TaskName
from unstract.sdk1.constants import MetadataKey, ToolEnv, UsageKwargs
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


def _apply_profile_overrides(
    tool_metadata: dict, profile_data: dict
) -> list[str]:
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
                change_desc = (
                    f"{section_name}.{section_key}: {old_value} -> {new_value}"
                )
                changes.append(change_desc)
                logger.info("Overrode %s", change_desc)
    return changes


def _should_skip_extraction_for_smart_table(
    input_file: str, outputs: list[dict[str, Any]]
) -> bool:
    """Check if extraction and indexing should be skipped for smart table.

    Standalone version of StructureTool._should_skip_extraction_for_smart_table.
    """
    for output in outputs:
        if _SK.TABLE_SETTINGS in output:
            prompt = output.get(_SK.PROMPT, "")
            if prompt and isinstance(prompt, str):
                try:
                    schema_data = json.loads(prompt)
                    if schema_data and isinstance(schema_data, dict):
                        return True
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(
                        "Failed to parse prompt as JSON for smart table: %s", e
                    )
                    continue
    return False


def _merge_metrics(metrics1: dict, metrics2: dict) -> dict:
    """Merge two metrics dicts, combining sub-dicts for shared keys."""
    merged: dict = {}
    all_keys = set(metrics1) | set(metrics2)
    for key in all_keys:
        if (
            key in metrics1
            and key in metrics2
            and isinstance(metrics1[key], dict)
            and isinstance(metrics2[key], dict)
        ):
            merged[key] = {**metrics1[key], **metrics2[key]}
        elif key in metrics1:
            merged[key] = metrics1[key]
        else:
            merged[key] = metrics2[key]
    return merged


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
        return ExecutionResult.failure(
            error=f"Structure tool failed: {e}"
        ).to_dict()


def _execute_structure_tool_impl(params: dict) -> dict:
    """Implementation of the structure tool pipeline.

    Separated from the task function for testability.
    """
    # ---- Unpack params ----
    organization_id = params["organization_id"]
    workflow_id = params.get("workflow_id", "")
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

    shim = ExecutorToolShim(platform_api_key=platform_service_api_key)

    platform_helper = _create_platform_helper(shim, file_execution_id)
    dispatcher = ExecutionDispatcher(celery_app=app)
    fs = _get_file_storage()

    # ---- Step 2: Fetch tool metadata ----
    prompt_registry_id = tool_instance_metadata.get(
        _SK.PROMPT_REGISTRY_ID, ""
    )
    logger.info(
        "Fetching exported tool with UUID '%s'", prompt_registry_id
    )

    tool_metadata, is_agentic = _fetch_tool_metadata(
        platform_helper, prompt_registry_id
    )

    # ---- Route agentic vs regular ----
    if is_agentic:
        return _run_agentic_extraction(
            tool_metadata=tool_metadata,
            input_file_path=input_file_path,
            output_dir_path=output_dir_path,
            tool_instance_metadata=tool_instance_metadata,
            dispatcher=dispatcher,
            shim=shim,
            platform_helper=platform_helper,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
            source_file_name=source_file_name,
            fs=fs,
        )

    # ---- Step 3: Profile overrides ----
    _handle_profile_overrides(
        exec_metadata, platform_helper, tool_metadata
    )

    # ---- Extract settings from tool_metadata ----
    settings = tool_instance_metadata
    is_challenge_enabled = settings.get(_SK.ENABLE_CHALLENGE, False)
    is_summarization_enabled = settings.get(_SK.SUMMARIZE_AS_SOURCE, False)
    is_single_pass_enabled = settings.get(
        _SK.SINGLE_PASS_EXTRACTION_MODE, False
    )
    challenge_llm = settings.get(_SK.CHALLENGE_LLM_ADAPTER_ID, "")
    is_highlight_enabled = settings.get(_SK.ENABLE_HIGHLIGHT, False)

    tool_id = tool_metadata[_SK.TOOL_ID]
    tool_settings = tool_metadata[_SK.TOOL_SETTINGS]
    outputs = tool_metadata[_SK.OUTPUTS]

    # Inject workflow-level settings into tool_settings
    tool_settings[_SK.CHALLENGE_LLM] = challenge_llm
    tool_settings[_SK.ENABLE_CHALLENGE] = is_challenge_enabled
    tool_settings[_SK.ENABLE_SINGLE_PASS_EXTRACTION] = is_single_pass_enabled
    tool_settings[_SK.SUMMARIZE_AS_SOURCE] = is_summarization_enabled
    tool_settings[_SK.ENABLE_HIGHLIGHT] = is_highlight_enabled

    _, file_name = os.path.split(input_file_path)
    if is_summarization_enabled:
        file_name = _SK.SUMMARIZE

    execution_run_data_folder = Path(execution_data_dir)
    extracted_input_file = str(execution_run_data_folder / _SK.EXTRACT)

    # ---- Step 4: Build payload ----
    custom_data = exec_metadata.get(_SK.CUSTOM_DATA, {})
    payload = {
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

    # ---- Step 5: Extract ----
    skip_extraction_and_indexing = _should_skip_extraction_for_smart_table(
        input_file_path, outputs
    )

    extracted_text = ""
    usage_kwargs: dict[Any, Any] = {}
    if skip_extraction_and_indexing:
        logger.info(
            "Skipping extraction and indexing for Excel table "
            "with valid JSON schema"
        )
    else:
        logger.info("Extracting document '%s'", source_file_name)
        usage_kwargs[UsageKwargs.RUN_ID] = file_execution_id
        usage_kwargs[UsageKwargs.FILE_NAME] = source_file_name
        usage_kwargs[UsageKwargs.EXECUTION_ID] = execution_id

        extract_ctx = ExecutionContext(
            executor_name="legacy",
            operation="extract",
            run_id=file_execution_id,
            execution_source="tool",
            organization_id=organization_id,
            request_id=file_execution_id,
            executor_params={
                "x2text_instance_id": tool_settings[_SK.X2TEXT_ADAPTER],
                "file_path": input_file_path,
                "enable_highlight": is_highlight_enabled,
                "output_file_path": str(
                    execution_run_data_folder / _SK.EXTRACT
                ),
                "platform_api_key": platform_service_api_key,
                "usage_kwargs": usage_kwargs,
                "tags": exec_metadata.get("tags"),
                "tool_execution_metadata": exec_metadata,
                "execution_data_dir": str(execution_run_data_folder),
            },
        )
        extract_result = dispatcher.dispatch(
            extract_ctx, timeout=EXECUTOR_TIMEOUT
        )
        if not extract_result.success:
            return extract_result.to_dict()
        extracted_text = extract_result.data.get("extracted_text", "")

    # ---- Step 6: Summarize (if enabled) ----
    index_metrics: dict = {}
    if is_summarization_enabled:
        summarize_file_path, summarize_file_hash = _summarize(
            tool_settings=tool_settings,
            tool_data_dir=execution_run_data_folder,
            dispatcher=dispatcher,
            outputs=outputs,
            usage_kwargs=usage_kwargs,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
            platform_service_api_key=platform_service_api_key,
            fs=fs,
        )
        payload[_SK.FILE_HASH] = summarize_file_hash
        payload[_SK.FILE_PATH] = summarize_file_path
    elif skip_extraction_and_indexing:
        # Use source file directly for Excel with valid JSON
        payload[_SK.FILE_PATH] = input_file_path
    elif not is_single_pass_enabled:
        # ---- Step 7: Index ----
        index_metrics = _index_documents(
            outputs=outputs,
            tool_settings=tool_settings,
            tool_id=tool_id,
            file_hash=file_hash,
            extracted_text=extracted_text,
            execution_run_data_folder=execution_run_data_folder,
            is_highlight_enabled=is_highlight_enabled,
            dispatcher=dispatcher,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
            platform_service_api_key=platform_service_api_key,
        )

    # ---- Step 8: Answer prompt (or single pass) ----
    if is_single_pass_enabled:
        logger.info("Fetching response for single pass extraction...")
        operation = "single_pass_extraction"
    else:
        # Handle table_settings injection
        for output in outputs:
            if _SK.TABLE_SETTINGS in output:
                table_settings = output[_SK.TABLE_SETTINGS]
                is_directory_mode = table_settings.get(
                    _SK.IS_DIRECTORY_MODE, False
                )
                if skip_extraction_and_indexing:
                    table_settings[_SK.INPUT_FILE] = input_file_path
                    payload[_SK.FILE_PATH] = input_file_path
                else:
                    table_settings[_SK.INPUT_FILE] = extracted_input_file
                table_settings[_SK.IS_DIRECTORY_MODE] = is_directory_mode
                logger.info(
                    "Performing table extraction with: %s", table_settings
                )
                output[_SK.TABLE_SETTINGS] = table_settings

        logger.info(
            "Fetching responses for '%d' prompt(s)...", len(outputs)
        )
        operation = "answer_prompt"

    answer_ctx = ExecutionContext(
        executor_name="legacy",
        operation=operation,
        run_id=file_execution_id,
        execution_source="tool",
        organization_id=organization_id,
        request_id=file_execution_id,
        executor_params=payload,
    )
    answer_result = dispatcher.dispatch(answer_ctx, timeout=EXECUTOR_TIMEOUT)
    if not answer_result.success:
        return answer_result.to_dict()

    structured_output = answer_result.data

    # ---- Step 9: Post-process and write output ----
    # Ensure metadata section exists
    if _SK.METADATA not in structured_output:
        structured_output[_SK.METADATA] = {}

    structured_output[_SK.METADATA][_SK.FILE_NAME] = source_file_name

    # Add extracted text for HITL raw view
    if extracted_text:
        structured_output[_SK.METADATA]["extracted_text"] = extracted_text
        logger.info(
            "Added extracted text to metadata (length: %d characters)",
            len(extracted_text),
        )

    # Merge index metrics
    if merged_metrics := _merge_metrics(
        structured_output.get(_SK.METRICS, {}), index_metrics
    ):
        structured_output[_SK.METRICS] = merged_metrics

    # Write output JSON
    try:
        output_path = (
            Path(output_dir_path)
            / f"{Path(source_file_name).stem}.json"
        )
        logger.info("Writing output to %s", output_path)
        fs.json_dump(path=output_path, data=structured_output)
        logger.info("Output written successfully to workflow storage")
    except (OSError, json.JSONDecodeError) as e:
        return ExecutionResult.failure(
            error=f"Error writing output file: {e}"
        ).to_dict()

    # Write tool result to METADATA.json
    _write_tool_result(fs, execution_data_dir, structured_output)

    return ExecutionResult(
        success=True, data=structured_output
    ).to_dict()


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


def _fetch_tool_metadata(
    platform_helper, prompt_registry_id: str
) -> tuple[dict, bool]:
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
        logger.info(
            "Not found as prompt studio project, trying agentic: %s", e
        )

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
            profile_name = llm_profile.get(
                "profile_name", llm_profile_id
            )
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
                logger.info(
                    "Profile overrides applied - no changes needed"
                )
    except Exception as e:
        raise RuntimeError(
            f"Error applying profile overrides: {e}"
        ) from e


def _summarize(
    tool_settings: dict,
    tool_data_dir: Path,
    dispatcher: ExecutionDispatcher,
    outputs: list[dict],
    usage_kwargs: dict,
    file_execution_id: str,
    organization_id: str,
    platform_service_api_key: str,
    fs: Any,
) -> tuple[str, str]:
    """Summarize the document, with filesystem caching.

    Returns:
        Tuple of (summarize_file_path, summarize_file_hash).
    """
    llm_adapter_instance_id = tool_settings[_SK.LLM]
    embedding_instance_id = tool_settings[_SK.EMBEDDING]
    vector_db_instance_id = tool_settings[_SK.VECTOR_DB]
    x2text_instance_id = tool_settings[_SK.X2TEXT_ADAPTER]
    summarize_prompt = tool_settings[_SK.SUMMARIZE_PROMPT]
    run_id = usage_kwargs.get(UsageKwargs.RUN_ID, file_execution_id)
    extract_file_path = tool_data_dir / _SK.EXTRACT
    summarize_file_path = tool_data_dir / _SK.SUMMARIZE

    # Check cache
    summarized_context = ""
    logger.info(
        "Checking if summarized context exists at '%s'...",
        summarize_file_path,
    )
    if fs.exists(summarize_file_path):
        summarized_context = fs.read(path=summarize_file_path, mode="r")

    if not summarized_context:
        context = fs.read(path=extract_file_path, mode="r")
        prompt_keys = []
        for output in outputs:
            prompt_keys.append(output[_SK.NAME])
            output[_SK.EMBEDDING] = embedding_instance_id
            output[_SK.VECTOR_DB] = vector_db_instance_id
            output[_SK.X2TEXT_ADAPTER] = x2text_instance_id
            output[_SK.CHUNK_SIZE] = 0
            output[_SK.CHUNK_OVERLAP] = 0

        logger.info("Summarized context not found, summarizing...")
        summarize_ctx = ExecutionContext(
            executor_name="legacy",
            operation="summarize",
            run_id=run_id,
            execution_source="tool",
            organization_id=organization_id,
            request_id=file_execution_id,
            executor_params={
                _SK.LLM_ADAPTER_INSTANCE_ID: llm_adapter_instance_id,
                _SK.SUMMARIZE_PROMPT: summarize_prompt,
                _SK.CONTEXT: context,
                _SK.PROMPT_KEYS: prompt_keys,
                "PLATFORM_SERVICE_API_KEY": platform_service_api_key,
            },
        )
        summarize_result = dispatcher.dispatch(
            summarize_ctx, timeout=EXECUTOR_TIMEOUT
        )
        if not summarize_result.success:
            raise RuntimeError(
                f"Summarization failed: {summarize_result.error}"
            )
        summarized_context = summarize_result.data.get(_SK.DATA, "")
        logger.info(
            "Writing summarized context to '%s'", summarize_file_path
        )
        fs.write(
            path=summarize_file_path, mode="w", data=summarized_context
        )

    summarize_file_hash = fs.get_hash_from_file(path=summarize_file_path)
    return str(summarize_file_path), summarize_file_hash


def _index_documents(
    outputs: list[dict],
    tool_settings: dict,
    tool_id: str,
    file_hash: str,
    extracted_text: str,
    execution_run_data_folder: Path,
    is_highlight_enabled: bool,
    dispatcher: ExecutionDispatcher,
    file_execution_id: str,
    organization_id: str,
    platform_service_api_key: str,
) -> dict:
    """Index documents with dedup on parameter combinations.

    Returns:
        Dict of index metrics per output name.
    """
    import datetime

    index_metrics: dict = {}
    seen_params: set = set()

    for output in outputs:
        chunk_size = output[_SK.CHUNK_SIZE]
        chunk_overlap = output[_SK.CHUNK_OVERLAP]
        vector_db = tool_settings[_SK.VECTOR_DB]
        embedding = tool_settings[_SK.EMBEDDING]
        x2text = tool_settings[_SK.X2TEXT_ADAPTER]

        param_key = (
            f"chunk_size={chunk_size}_"
            f"chunk_overlap={chunk_overlap}_"
            f"vector_db={vector_db}_"
            f"embedding={embedding}_"
            f"x2text={x2text}"
        )

        if chunk_size != 0 and param_key not in seen_params:
            seen_params.add(param_key)

            indexing_start_time = datetime.datetime.now()
            logger.info(
                "Indexing document with: chunk_size=%s, "
                "chunk_overlap=%s, vector_db=%s, embedding=%s, "
                "x2text=%s",
                chunk_size,
                chunk_overlap,
                vector_db,
                embedding,
                x2text,
            )

            index_ctx = ExecutionContext(
                executor_name="legacy",
                operation="index",
                run_id=file_execution_id,
                execution_source="tool",
                organization_id=organization_id,
                request_id=file_execution_id,
                executor_params={
                    "embedding_instance_id": embedding,
                    "vector_db_instance_id": vector_db,
                    "x2text_instance_id": x2text,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "file_path": str(
                        execution_run_data_folder / _SK.EXTRACT
                    ),
                    "reindex": True,
                    "tool_id": tool_id,
                    "file_hash": file_hash,
                    "enable_highlight": is_highlight_enabled,
                    "extracted_text": extracted_text,
                    "platform_api_key": platform_service_api_key,
                },
            )
            index_result = dispatcher.dispatch(
                index_ctx, timeout=EXECUTOR_TIMEOUT
            )
            if not index_result.success:
                logger.warning(
                    "Indexing failed for param combo %s: %s",
                    param_key,
                    index_result.error,
                )

            elapsed = (
                datetime.datetime.now() - indexing_start_time
            ).total_seconds()
            index_metrics[output[_SK.NAME]] = {
                _SK.INDEXING: {"time_taken(s)": elapsed}
            }

    return index_metrics


def _run_agentic_extraction(
    tool_metadata: dict,
    input_file_path: str,
    output_dir_path: str,
    tool_instance_metadata: dict,
    dispatcher: ExecutionDispatcher,
    shim: Any,
    platform_helper: Any,
    file_execution_id: str,
    organization_id: str,
    source_file_name: str,
    fs: Any,
) -> dict:
    """Execute agentic extraction pipeline via dispatcher.

    Currently returns failure since the agentic extraction plugin
    is not yet available in the executor worker.
    """
    agentic_ctx = ExecutionContext(
        executor_name="legacy",
        operation="agentic_extraction",
        run_id=file_execution_id,
        execution_source="tool",
        organization_id=organization_id,
        request_id=file_execution_id,
        executor_params={
            "tool_metadata": tool_metadata,
            "input_file_path": input_file_path,
            "tool_instance_metadata": tool_instance_metadata,
        },
    )
    agentic_result = dispatcher.dispatch(
        agentic_ctx, timeout=EXECUTOR_TIMEOUT
    )
    return agentic_result.to_dict()


def _write_tool_result(
    fs: Any, execution_data_dir: str, data: dict
) -> None:
    """Write tool result to METADATA.json (matches BaseTool.write_tool_result)."""
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

        # Add tool result
        existing["tool_result"] = data
        fs.write(
            path=metadata_path,
            mode="w",
            data=json.dumps(existing, indent=2),
        )
    except Exception as e:
        logger.warning("Failed to write tool result to METADATA.json: %s", e)
