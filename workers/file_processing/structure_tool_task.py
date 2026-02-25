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

    Phase 5E: Uses a single ``structure_pipeline`` dispatch instead of
    3 sequential ``dispatcher.dispatch()`` calls.  The executor worker
    handles the full extract → summarize → index → answer_prompt
    pipeline internally, freeing the file_processing worker slot.
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

    # ---- Step 4: Smart table detection ----
    skip_extraction_and_indexing = _should_skip_extraction_for_smart_table(
        input_file_path, outputs
    )
    if skip_extraction_and_indexing:
        logger.info(
            "Skipping extraction and indexing for Excel table "
            "with valid JSON schema"
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
            "summarize_prompt": tool_settings.get(
                _SK.SUMMARIZE_PROMPT, ""
            ),
            "extract_file_path": str(
                execution_run_data_folder / _SK.EXTRACT
            ),
            "summarize_file_path": str(
                execution_run_data_folder / _SK.SUMMARIZE
            ),
            "platform_api_key": platform_service_api_key,
            "prompt_keys": prompt_keys,
        }

    # ---- Step 6: Single dispatch to executor ----
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
        executor_params={
            "extract_params": extract_params,
            "index_template": index_template,
            "answer_params": answer_params,
            "pipeline_options": pipeline_options,
            "summarize_params": summarize_params,
        },
    )
    pipeline_result = dispatcher.dispatch(
        pipeline_ctx, timeout=EXECUTOR_TIMEOUT
    )
    if not pipeline_result.success:
        return pipeline_result.to_dict()

    structured_output = pipeline_result.data

    # ---- Step 7: Write output files ----
    # (metadata/metrics merging already done by executor pipeline)
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
