"""Structure Worker Tasks

Celery task for structure extraction using SDK1 classes.
Duplicates logic from tools/structure/src/main.py adapted for worker context.
"""

import datetime
import json
import os
from pathlib import Path
from typing import Any

from celery import shared_task
from constants import SettingsKeys
from helpers import StructureToolHelper as STHelper
from shared.infrastructure.logging import (
    WorkerLogger,
    WorkerWorkflowLogger,
    with_execution_context,
)
from utils import json_to_markdown, repair_json_with_best_structure

from unstract.sdk1.constants import (
    LogLevel,
    LogState,
    MetadataKey,
    ToolEnv,
    UsageKwargs,
)
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.prompt import PromptTool
from unstract.sdk1.x2txt import X2Text
from unstract.workflow_execution.enums import LogStage

logger = WorkerLogger.get_logger(__name__)

PAID_FEATURE_MSG = (
    "It is a cloud / enterprise feature. If you have purchased a plan and still "
    "face this issue, please contact support"
)


class WorkerToolContext:
    """Minimal tool-like object for SDK1 classes in worker context.

    Provides the 3 methods SDK1 classes need:
    - get_env_or_die(key): Get environment variable
    - stream_log(msg, level): Log messages  (streams to UI via WebSocket)
    - stream_error_and_exit(msg, err): Handle errors
    """

    def __init__(
        self,
        platform_api_key: str,
        file_execution_id: str,
        execution_id: str,
        organization_id: str,
        source_file_name: str,
        tags: list[str],
        exec_metadata: dict[str, Any],
    ):
        """Initialize worker tool context.

        Args:
            platform_api_key: Platform API key for authentication
            file_execution_id: File execution ID (used as request_id)
            execution_id: Execution ID
            organization_id: Organization ID for WebSocket routing
            source_file_name: Source file name
            tags: Tags for the execution
            exec_metadata: Execution metadata
        """
        self._platform_api_key = platform_api_key
        self.file_execution_id = file_execution_id
        self.execution_id = execution_id
        self.source_file_name = source_file_name
        self.tags = tags
        self._exec_metadata = exec_metadata

        # Create WorkerWorkflowLogger for UI log streaming
        self._workflow_logger = WorkerWorkflowLogger(
            execution_id=execution_id,
            log_stage=LogStage.RUN,
            file_execution_id=file_execution_id,
            organization_id=organization_id,
        )

    def get_env_or_die(self, env_key: str) -> str:
        """Get environment variable or raise error.

        Args:
            env_key: Environment variable key

        Returns:
            Environment variable value

        Raises:
            SdkError: If environment variable is not set
        """
        # Special handling for PLATFORM_API_KEY - use the one passed to task
        if env_key == ToolEnv.PLATFORM_API_KEY:
            return self._platform_api_key

        env_value = os.environ.get(env_key)
        if env_value is None or env_value == "":
            raise SdkError(f"Environment variable '{env_key}' is required")
        return env_value

    def stream_log(
        self,
        log: str,
        level: LogLevel = LogLevel.INFO,
        stage: str = "TOOL_RUN",
        **kwargs: Any,
    ) -> None:
        """Log message using worker logger AND stream to UI via WebSocket.

        Args:
            log: Log message
            level: Log level (INFO, DEBUG, WARN, ERROR)
            stage: Log stage (ignored in worker context)
            **kwargs: Additional arguments (ignored)
        """
        # Stream to UI via WebSocket using WorkerWorkflowLogger
        from unstract.workflow_execution.enums import LogLevel as WorkflowLogLevel

        # Map SDK1 LogLevel to Workflow LogLevel
        workflow_level = WorkflowLogLevel.INFO
        if level == LogLevel.ERROR or level == LogLevel.FATAL:
            workflow_level = WorkflowLogLevel.ERROR

        # Publish to UI
        self._workflow_logger.publish_log(log, level=workflow_level)

        # Also log to backend for debugging
        if level == LogLevel.DEBUG:
            logger.debug(log)
        elif level == LogLevel.WARN:
            logger.warning(log)
        elif level == LogLevel.ERROR:
            logger.error(log)
        elif level == LogLevel.FATAL:
            logger.critical(log)
        else:  # INFO
            logger.info(log)

    def stream_update(self, message: str, state: LogState, **kwargs: Any) -> None:
        """Stream status update to UI (INPUT_UPDATE, OUTPUT_UPDATE).

        Args:
            message: Status update message
            state: LogState (INPUT_UPDATE, OUTPUT_UPDATE, etc.)
            **kwargs: Additional arguments (ignored)
        """
        # Publish update log to UI via WebSocket
        self._workflow_logger.publish_update_log(
            state=state, message=message, component=None
        )

        # Also log to backend
        logger.info(f"[{state.value}] {message}")

    def stream_error_and_exit(
        self, message: str, err: Exception | None = None, **kwargs: Any
    ) -> None:
        """Log error and raise exception.

        Args:
            message: Error message
            err: Original exception (if any)
            **kwargs: Additional arguments (ignored)

        Raises:
            SdkError: Always raises with the error message
        """
        logger.error(f"{message}: {err}" if err else message)
        raise SdkError(message, actual_err=err)

    @property
    def get_exec_metadata(self) -> dict[str, Any]:
        """Get execution metadata.

        Returns:
            Execution metadata dictionary
        """
        return self._exec_metadata


@shared_task(
    name="structure.execute_extraction",
    bind=True,
    time_limit=7200,  # 2 hours
    soft_time_limit=7000,
    autoretry_for=(ConnectionError,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
@with_execution_context
def execute_structure_extraction(
    self,
    settings: dict[str, Any],
    file_execution_id: str,
    organization_id: str,
    workflow_id: str,
    tool_instance_id: str,
    platform_api_key: str,
    execution_id: str,
    source_file_name: str,
    input_file_path: str,
    output_dir: str,
    exec_metadata: dict[str, Any],
    tags: list[str],
) -> dict[str, Any]:
    """Execute structure extraction task.

    This duplicates the logic from tools/structure/src/main.py but uses
    SDK1 classes in a worker context via WorkerToolContext.

    Args:
        settings: Tool instance settings (contains prompt_registry_id, etc.)
        file_execution_id: File execution ID
        organization_id: Organization ID
        workflow_id: Workflow ID
        tool_instance_id: Tool instance ID
        platform_api_key: Platform API key for authentication
        execution_id: Execution ID
        source_file_name: Source file name
        input_file_path: Path to input file in storage
        output_dir: Output directory in storage
        exec_metadata: Execution metadata
        tags: Execution tags

    Returns:
        Dictionary containing:
        - output: Extraction results
        - metadata: File metadata, metrics
        - status: "success" or "error"
    """
    logger.info(
        f"Starting structure extraction for file_execution_id={file_execution_id}, "
        f"source={source_file_name}"
    )

    # Create worker tool context for SDK1 classes
    tool_context = WorkerToolContext(
        platform_api_key=platform_api_key,
        file_execution_id=file_execution_id,
        execution_id=execution_id,
        organization_id=organization_id,
        source_file_name=source_file_name,
        tags=tags,
        exec_metadata=exec_metadata,
    )

    # Initialize file storage
    file_storage = FileStorage(provider=FileStorageProvider.WORKFLOW_EXECUTION)

    # Extract settings
    prompt_registry_id: str = settings[SettingsKeys.PROMPT_REGISTRY_ID]
    is_challenge_enabled: bool = settings.get(SettingsKeys.ENABLE_CHALLENGE, False)
    is_summarization_enabled: bool = settings.get(SettingsKeys.SUMMARIZE_AS_SOURCE, False)
    is_single_pass_enabled: bool = settings.get(
        SettingsKeys.SINGLE_PASS_EXTRACTION_MODE, False
    )
    challenge_llm: str = settings.get(SettingsKeys.CHALLENGE_LLM_ADAPTER_ID, "")
    is_highlight_enabled: bool = settings.get(SettingsKeys.ENABLE_HIGHLIGHT, False)

    # Create SDK1 service clients using WorkerToolContext
    prompt_host = os.getenv(SettingsKeys.PROMPT_HOST, "prompt-service")
    prompt_port = os.getenv(SettingsKeys.PROMPT_PORT, "3003")
    platform_host = os.getenv(ToolEnv.PLATFORM_HOST, "backend")
    platform_port = os.getenv(ToolEnv.PLATFORM_PORT, "8000")

    responder: PromptTool = PromptTool(
        tool=tool_context,
        prompt_host=prompt_host,
        prompt_port=prompt_port,
        request_id=file_execution_id,
    )

    platform_helper: PlatformHelper = PlatformHelper(
        tool=tool_context,
        platform_host=platform_host,
        platform_port=platform_port,
        request_id=file_execution_id,
    )

    logger.info(f"Fetching exported tool with UUID '{prompt_registry_id}'")

    # Try to fetch as prompt studio tool first
    tool_metadata = None
    is_agentic = False
    exported_tool = None

    try:
        exported_tool = platform_helper.get_prompt_studio_tool(
            prompt_registry_id=prompt_registry_id
        )
    except Exception as e:
        logger.info(f"Not found as prompt studio project, trying agentic registry: {e}")

    if exported_tool and SettingsKeys.TOOL_METADATA in exported_tool:
        tool_metadata = exported_tool[SettingsKeys.TOOL_METADATA]
        is_agentic = False
        tool_metadata["is_agentic"] = False
    else:
        # Try agentic registry as fallback
        try:
            agentic_tool = platform_helper.get_agentic_studio_tool(
                agentic_registry_id=prompt_registry_id
            )
            if not agentic_tool or SettingsKeys.TOOL_METADATA not in agentic_tool:
                raise SdkError(
                    f"Error fetching project: Registry returned empty response for {prompt_registry_id}"
                )
            tool_metadata = agentic_tool[SettingsKeys.TOOL_METADATA]
            is_agentic = True
            tool_metadata["is_agentic"] = True
            logger.info(
                f"Retrieved agentic project: {tool_metadata.get('name', prompt_registry_id)}"
            )
        except Exception as agentic_error:
            raise SdkError(
                f"Error fetching project from both registries for ID '{prompt_registry_id}': {agentic_error}"
            )

    # Route to appropriate extraction method
    if is_agentic:
        return _run_agentic_extraction(
            tool_context=tool_context,
            tool_metadata=tool_metadata,
            input_file_path=input_file_path,
            output_dir=output_dir,
            settings=settings,
            responder=responder,
            platform_helper=platform_helper,
            file_storage=file_storage,
        )

    # Continue with regular prompt studio extraction
    llm_profile_id = exec_metadata.get(SettingsKeys.LLM_PROFILE_ID)
    llm_profile_to_override = None
    try:
        if llm_profile_id:
            llm_profile = platform_helper.get_llm_profile(llm_profile_id)
            llm_profile_to_override = llm_profile

        # Apply profile overrides if available
        if llm_profile_to_override:
            logger.info(
                f"Applying profile overrides from profile: {llm_profile_to_override.get('profile_name', llm_profile_id)}"
            )
            # Apply overrides using helper (this matches tools/structure pattern)
            _apply_profile_overrides(tool_metadata, llm_profile_to_override)
    except Exception as e:
        raise SdkError(f"Error fetching prompt studio project: {e}")

    ps_project_name = tool_metadata.get("name", prompt_registry_id)
    total_prompt_count = len(tool_metadata[SettingsKeys.OUTPUTS])
    logger.info(
        f"Retrieved prompt studio exported tool '{ps_project_name}' having "
        f"'{total_prompt_count}' prompts"
    )

    # Count active prompts and show UI status updates (matching original tool)
    active_prompt_count = len(
        [
            output
            for output in tool_metadata[SettingsKeys.OUTPUTS]
            if output.get("active", False)
        ]
    )

    # Update GUI with loaded project info
    input_log = f"## Loaded '{ps_project_name}'\n{json_to_markdown(tool_metadata)}\n"
    output_log = (
        f"## Processing '{source_file_name}'\nThis might take a while and "
        "involve...\n- Extracting text\n- Indexing\n- Retrieving answers "
        f"for '{active_prompt_count}' prompts"
    )
    tool_context.stream_update(input_log, state=LogState.INPUT_UPDATE)
    tool_context.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

    file_hash = exec_metadata.get(MetadataKey.SOURCE_HASH, "")
    tool_id = tool_metadata[SettingsKeys.TOOL_ID]
    tool_settings = tool_metadata[SettingsKeys.TOOL_SETTINGS]
    outputs = tool_metadata[SettingsKeys.OUTPUTS]
    tool_settings[SettingsKeys.CHALLENGE_LLM] = challenge_llm
    tool_settings[SettingsKeys.ENABLE_CHALLENGE] = is_challenge_enabled
    tool_settings[SettingsKeys.ENABLE_SINGLE_PASS_EXTRACTION] = is_single_pass_enabled
    tool_settings[SettingsKeys.SUMMARIZE_AS_SOURCE] = is_summarization_enabled
    tool_settings[SettingsKeys.ENABLE_HIGHLIGHT] = is_highlight_enabled

    _, file_name = os.path.split(input_file_path)
    if is_summarization_enabled:
        file_name = SettingsKeys.SUMMARIZE

    # Create temporary workspace for execution
    tool_data_dir = Path(f"/tmp/structure_{file_execution_id}")
    tool_data_dir.mkdir(parents=True, exist_ok=True)
    execution_run_data_folder = tool_data_dir

    extracted_input_file = str(execution_run_data_folder / SettingsKeys.EXTRACT)

    # Build payload
    payload = {
        SettingsKeys.RUN_ID: file_execution_id,
        SettingsKeys.EXECUTION_ID: execution_id,
        SettingsKeys.TOOL_SETTINGS: tool_settings,
        SettingsKeys.OUTPUTS: outputs,
        SettingsKeys.TOOL_ID: tool_id,
        SettingsKeys.FILE_HASH: file_hash,
        SettingsKeys.FILE_NAME: file_name,
        SettingsKeys.FILE_PATH: extracted_input_file,
        SettingsKeys.EXECUTION_SOURCE: SettingsKeys.TOOL,
    }

    custom_data = exec_metadata.get(SettingsKeys.CUSTOM_DATA, {})
    payload["custom_data"] = custom_data

    # Check if we should skip extraction for smart table
    skip_extraction_and_indexing = _should_skip_extraction_for_smart_table(
        input_file_path, outputs
    )

    extracted_text = ""
    usage_kwargs: dict[Any, Any] = {}
    if skip_extraction_and_indexing:
        logger.info(
            "Skipping extraction and indexing for Excel table with valid JSON schema"
        )
    else:
        logger.info(f"Extracting document '{source_file_name}'")
        usage_kwargs[UsageKwargs.RUN_ID] = file_execution_id
        usage_kwargs[UsageKwargs.FILE_NAME] = source_file_name
        usage_kwargs[UsageKwargs.EXECUTION_ID] = execution_id
        extracted_text = STHelper.dynamic_extraction(
            file_path=input_file_path,
            enable_highlight=is_highlight_enabled,
            usage_kwargs=usage_kwargs,
            run_id=file_execution_id,
            tool_settings=tool_settings,
            extract_file_path=tool_data_dir / SettingsKeys.EXTRACT,
            tool=tool_context,
            execution_run_data_folder=str(execution_run_data_folder),
        )

    index_metrics = {}
    if is_summarization_enabled:
        summarize_file_path, summarize_file_hash = _summarize(
            tool_context=tool_context,
            tool_settings=tool_settings,
            tool_data_dir=tool_data_dir,
            responder=responder,
            outputs=outputs,
            usage_kwargs=usage_kwargs,
            file_storage=file_storage,
        )
        payload[SettingsKeys.FILE_HASH] = summarize_file_hash
        payload[SettingsKeys.FILE_PATH] = summarize_file_path
    elif skip_extraction_and_indexing:
        payload[SettingsKeys.FILE_PATH] = input_file_path
    elif not is_single_pass_enabled:
        # Track seen parameter combinations
        seen_params = set()

        for output in outputs:
            chunk_size = output[SettingsKeys.CHUNK_SIZE]
            chunk_overlap = output[SettingsKeys.CHUNK_OVERLAP]
            vector_db = tool_settings[SettingsKeys.VECTOR_DB]
            embedding = tool_settings[SettingsKeys.EMBEDDING]
            x2text = tool_settings[SettingsKeys.X2TEXT_ADAPTER]

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
                    f"Indexing document with: chunk_size={chunk_size}, "
                    f"chunk_overlap={chunk_overlap}, vector_db={vector_db}, "
                    f"embedding={embedding}, x2text={x2text}"
                )

                STHelper.dynamic_indexing(
                    tool_settings=tool_settings,
                    run_id=file_execution_id,
                    file_path=tool_data_dir / SettingsKeys.EXTRACT,
                    tool=tool_context,
                    execution_run_data_folder=str(execution_run_data_folder),
                    chunk_overlap=chunk_overlap,
                    reindex=True,
                    usage_kwargs=usage_kwargs,
                    enable_highlight=is_highlight_enabled,
                    chunk_size=chunk_size,
                    tool_id=tool_metadata[SettingsKeys.TOOL_ID],
                    file_hash=file_hash,
                    extracted_text=extracted_text,
                )

                index_metrics[output[SettingsKeys.NAME]] = {
                    SettingsKeys.INDEXING: {
                        "time_taken(s)": (
                            datetime.datetime.now() - indexing_start_time
                        ).total_seconds()
                    }
                }

    if is_single_pass_enabled:
        logger.info("Fetching response for single pass extraction...")
        structured_output = responder.single_pass_extraction(payload=payload)
    else:
        for output in outputs:
            if SettingsKeys.TABLE_SETTINGS in output:
                table_settings = output[SettingsKeys.TABLE_SETTINGS]
                is_directory_mode: bool = table_settings.get(
                    SettingsKeys.IS_DIRECTORY_MODE, False
                )
                if skip_extraction_and_indexing:
                    table_settings[SettingsKeys.INPUT_FILE] = input_file_path
                    payload[SettingsKeys.FILE_PATH] = input_file_path
                else:
                    table_settings[SettingsKeys.INPUT_FILE] = extracted_input_file
                table_settings[SettingsKeys.IS_DIRECTORY_MODE] = is_directory_mode
                logger.info(f"Performing table extraction with: {table_settings}")
                output.update({SettingsKeys.TABLE_SETTINGS: table_settings})

        logger.info(f"Fetching responses for '{len(outputs)}' prompt(s)...")
        structured_output = responder.answer_prompt(payload=payload)

    # Ensure metadata section exists
    if SettingsKeys.METADATA not in structured_output:
        structured_output[SettingsKeys.METADATA] = {}

    structured_output[SettingsKeys.METADATA][SettingsKeys.FILE_NAME] = source_file_name

    # Add extracted text for HITL raw view
    if extracted_text:
        structured_output[SettingsKeys.METADATA]["extracted_text"] = extracted_text
        logger.info(
            f"Added text extracted from the document to metadata (length: {len(extracted_text)} characters)"
        )

    if merged_metrics := _merge_metrics(
        structured_output.get(SettingsKeys.METRICS, {}), index_metrics
    ):
        structured_output[SettingsKeys.METRICS] = merged_metrics

    try:
        logger.info("Writing prompt studio project's output to workflow's storage")
        output_path = Path(output_dir) / f"{Path(source_file_name).stem}.json"
        file_storage.json_dump(path=output_path, data=structured_output)
        logger.info(
            "Prompt studio project's output written successfully to workflow's storage"
        )
    except OSError as e:
        raise SdkError(f"Error creating output file: {e}")
    except json.JSONDecodeError as e:
        raise SdkError(f"Error encoding JSON: {e}")

    # CRITICAL: Write to INFILE for next tool in workflow chain
    # INFILE is in the parent directory (file_execution_dir)
    try:
        logger.info("Writing result to INFILE for next tool in workflow")
        # Remove tool_instance_id from path to get file_execution_dir
        file_execution_dir = (
            Path(output_dir).parent if tool_instance_id else Path(output_dir)
        )
        infile_path = file_execution_dir / "INFILE"
        file_storage.json_dump(path=infile_path, data=structured_output)
        logger.info("Result written to INFILE successfully")
    except OSError as e:
        raise SdkError(f"Error writing INFILE: {e}")
    except json.JSONDecodeError as e:
        raise SdkError(f"Error encoding INFILE JSON: {e}")

    logger.info(f"Structure extraction completed successfully for {source_file_name}")
    return structured_output


def _apply_profile_overrides(tool_metadata: dict, profile_data: dict) -> list[str]:
    """Apply profile overrides to tool metadata."""
    changes = []
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
        for profile_key, section_key in profile_to_tool_mapping.items():
            if (
                profile_key in profile_data
                and section_key in tool_metadata["tool_settings"]
            ):
                old_value = tool_metadata["tool_settings"][section_key]
                new_value = profile_data[profile_key]
                if old_value != new_value:
                    tool_metadata["tool_settings"][section_key] = new_value
                    changes.append(
                        f"tool_settings.{section_key}: {old_value} -> {new_value}"
                    )

    if "outputs" in tool_metadata:
        for i, output in enumerate(tool_metadata["outputs"]):
            output_name = output.get("name", f"output_{i}")
            for profile_key, section_key in profile_to_tool_mapping.items():
                if profile_key in profile_data and section_key in output:
                    old_value = output[section_key]
                    new_value = profile_data[profile_key]
                    if old_value != new_value:
                        output[section_key] = new_value
                        changes.append(
                            f"output[{output_name}].{section_key}: {old_value} -> {new_value}"
                        )

    return changes


def _should_skip_extraction_for_smart_table(
    input_file: str, outputs: list[dict[str, Any]]
) -> bool:
    """Check if extraction should be skipped for smart table."""
    for output in outputs:
        if SettingsKeys.TABLE_SETTINGS in output:
            prompt = output.get(SettingsKeys.PROMPT, "")
            if prompt and isinstance(prompt, str):
                try:
                    schema_data = repair_json_with_best_structure(prompt)
                    if schema_data and isinstance(schema_data, dict):
                        return True
                except Exception as e:
                    logger.warning(
                        f"Failed to parse prompt as JSON for smart table extraction: {e}"
                    )
                    continue
    return False


def _merge_metrics(metrics1: dict, metrics2: dict) -> dict:
    """Intelligently merge two metrics dictionaries."""
    merged_metrics = {}
    all_keys = set(metrics1) | set(metrics2)

    for key in all_keys:
        if (
            key in metrics1
            and key in metrics2
            and isinstance(metrics1[key], dict)
            and isinstance(metrics2[key], dict)
        ):
            merged_metrics[key] = {**metrics1[key], **metrics2[key]}
        elif key in metrics1:
            merged_metrics[key] = metrics1[key]
        else:
            merged_metrics[key] = metrics2[key]

    return merged_metrics


def _run_agentic_extraction(
    tool_context: WorkerToolContext,
    tool_metadata: dict[str, Any],
    input_file_path: str,
    output_dir: str,
    settings: dict[str, Any],
    responder: PromptTool,
    platform_helper: PlatformHelper,
    file_storage: FileStorage,
) -> dict[str, Any]:
    """Execute agentic extraction pipeline."""
    project_id = tool_metadata.get("project_id")
    project_name = tool_metadata.get("name", project_id)
    json_schema = tool_metadata.get("json_schema", {})
    prompt_text = tool_metadata.get("prompt_text", "")
    prompt_version = tool_metadata.get("prompt_version", 1)
    schema_version = tool_metadata.get("schema_version", 1)
    adapter_config = tool_metadata.get("adapter_config", {})

    logger.info(
        f"Executing agentic extraction for project '{project_name}' "
        f"(schema v{schema_version}, prompt v{prompt_version})"
    )

    # Get adapter IDs
    extractor_llm = settings.get(
        "extractor_llm_adapter_id", adapter_config.get("extractor_llm")
    )
    llmwhisperer = settings.get(
        "llmwhisperer_adapter_id", adapter_config.get("llmwhisperer")
    )
    enable_highlight = settings.get(
        SettingsKeys.ENABLE_HIGHLIGHT, tool_metadata.get("enable_highlight", False)
    )

    # Get platform details for organization_id
    platform_details = platform_helper.get_platform_details()
    organization_id = (
        platform_details.get("organization_id") if platform_details else None
    )

    if not organization_id:
        raise SdkError("Failed to get organization_id from platform")

    # Extract text from document using X2Text
    logger.info("Extracting text from document...")
    x2text = X2Text(tool=tool_context, adapter_instance_id=llmwhisperer)

    extraction_result = x2text.process(
        input_file_path=input_file_path,
        enable_highlight=enable_highlight,
        fs=file_storage,
    )

    document_text = extraction_result.extracted_text
    line_metadata = (
        extraction_result.extraction_metadata.line_metadata
        if extraction_result.extraction_metadata
        else None
    )

    logger.info(f"Extracted {len(document_text)} characters of text")

    # Build extraction payload
    payload = {
        "document_id": tool_context.file_execution_id,
        "prompt_text": prompt_text,
        "document_text": document_text,
        "schema": json_schema,
        "organization_id": organization_id,
        "adapter_instance_id": extractor_llm,
        "include_source_refs": enable_highlight,
    }

    if line_metadata and enable_highlight:
        payload["line_metadata"] = line_metadata
        logger.info(
            f"Including {len(line_metadata)} line metadata entries for highlighting"
        )

    # Call agentic extraction endpoint
    logger.info("Calling agentic extraction endpoint...")
    extraction_response = responder.agentic_extraction(payload=payload)

    # Process response
    extracted_data = extraction_response.get(SettingsKeys.OUTPUT, {})

    # Remove _source_refs from extracted data
    try:
        extracted_data = _remove_source_refs(extracted_data)
    except Exception as e:
        logger.warning(
            f"Warning: Failed to remove _source_refs: {e}. Proceeding with original data."
        )

    # Build final structured output
    structured_output = {
        SettingsKeys.OUTPUT: extracted_data,
        SettingsKeys.METADATA: {
            **extraction_response.get(SettingsKeys.METADATA, {}),
            SettingsKeys.FILE_NAME: tool_context.source_file_name,
            "project_id": project_id,
            "schema_version": schema_version,
            "prompt_version": prompt_version,
            "document_id": tool_context.file_execution_id,
        },
    }

    # Write output to file
    logger.info("Writing agentic extraction output to workflow storage")
    output_path = Path(output_dir) / f"{Path(tool_context.source_file_name).stem}.json"
    file_storage.json_dump(path=output_path, data=structured_output)
    logger.info("Output written successfully to workflow storage")

    return structured_output


def _remove_source_refs(data: Any) -> Any:
    """Recursively remove _source_refs from data structure."""
    if isinstance(data, dict):
        return {
            key: _remove_source_refs(value)
            for key, value in data.items()
            if key != "_source_refs"
        }
    elif isinstance(data, list):
        return [_remove_source_refs(item) for item in data]
    else:
        return data


def _summarize(
    tool_context: WorkerToolContext,
    tool_settings: dict[str, Any],
    tool_data_dir: Path,
    responder: PromptTool,
    outputs: dict[str, Any],
    usage_kwargs: dict[Any, Any],
    file_storage: FileStorage,
) -> tuple[str, str]:
    """Summarizes the context of the file."""
    llm_adapter_instance_id: str = tool_settings[SettingsKeys.LLM]
    embedding_instance_id: str = tool_settings[SettingsKeys.EMBEDDING]
    vector_db_instance_id: str = tool_settings[SettingsKeys.VECTOR_DB]
    x2text_instance_id: str = tool_settings[SettingsKeys.X2TEXT_ADAPTER]
    summarize_prompt: str = tool_settings[SettingsKeys.SUMMARIZE_PROMPT]
    run_id: str = usage_kwargs.get(UsageKwargs.RUN_ID)
    extract_file_path = tool_data_dir / SettingsKeys.EXTRACT
    summarize_file_path = tool_data_dir / SettingsKeys.SUMMARIZE

    summarized_context = ""
    logger.info(f"Checking if summarized context exists at '{summarize_file_path}'...")
    if file_storage.exists(summarize_file_path):
        summarized_context = file_storage.read(path=summarize_file_path, mode="r")

    if not summarized_context:
        context = file_storage.read(path=extract_file_path, mode="r")
        prompt_keys = []
        for output in outputs:
            prompt_keys.append(output[SettingsKeys.NAME])
            output[SettingsKeys.EMBEDDING] = embedding_instance_id
            output[SettingsKeys.VECTOR_DB] = vector_db_instance_id
            output[SettingsKeys.X2TEXT_ADAPTER] = x2text_instance_id
            output[SettingsKeys.CHUNK_SIZE] = 0
            output[SettingsKeys.CHUNK_OVERLAP] = 0
        logger.info("Summarized context not found, summarizing...")
        payload = {
            SettingsKeys.RUN_ID: run_id,
            SettingsKeys.LLM_ADAPTER_INSTANCE_ID: llm_adapter_instance_id,
            SettingsKeys.SUMMARIZE_PROMPT: summarize_prompt,
            SettingsKeys.CONTEXT: context,
            SettingsKeys.PROMPT_KEYS: prompt_keys,
        }
        structure_output = responder.summarize(payload=payload)
        summarized_context = structure_output.get(SettingsKeys.DATA, "")
        logger.info(f"Writing summarized context to '{summarize_file_path}'")
        file_storage.write(path=summarize_file_path, mode="w", data=summarized_context)

    summarize_file_hash: str = file_storage.get_hash_from_file(path=summarize_file_path)
    return str(summarize_file_path), summarize_file_hash
