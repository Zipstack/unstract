"""WorkflowExecutionService Integration for Workers

This module provides direct integration with the WorkflowExecutionService
from unstract/workflow-execution, enabling workers to execute workflows
directly using the ToolSandbox and runner services.
"""

import os
import time
from typing import Any

import magic
from shared.enums.file_types import AllowedFileTypes
from shared.exceptions.execution_exceptions import (
    NotFoundDestinationConfiguration,
    NotFoundSourceConfiguration,
)
from shared.exceptions.file_exceptions import EmptyFileError, UnsupportedMimeTypeError
from shared.models.file_processing import FileProcessingContext

# Import shared dataclasses for type safety and consistency
from unstract.core.data_models import (
    # DestinationConfig, # remove once verified
    FileHashData,
    FileOperationConstants,
    WorkflowDefinitionResponseData,
    WorkflowEndpointConfigData,
)

# Import file execution tracking for proper recovery mechanism
from unstract.core.file_execution_tracker import (
    FileExecutionData,
    FileExecutionStage,
    FileExecutionStageData,
    FileExecutionStageStatus,
    FileExecutionStatusTracker,
)
from unstract.core.tool_execution_status import (
    ToolExecutionData,
    ToolExecutionTracker,
)
from unstract.core.worker_models import (
    FinalOutputResult,
    WorkflowExecutionMetadata,
    WorkflowExecutionResult,
)
from unstract.workflow_execution.dto import ToolInstance, WorkflowDto
from unstract.workflow_execution.execution_file_handler import ExecutionFileHandler

# Direct imports now that dependencies are properly configured
from unstract.workflow_execution.workflow_execution import WorkflowExecutionService

from ...api.internal_client import InternalAPIClient
from ...infrastructure.logging import WorkerLogger
from ..destination_connector import (
    DestinationConfig,
    WorkerDestinationConnector,
)

logger = WorkerLogger.get_logger(__name__)


class WorkerWorkflowExecutionService:
    """Worker-compatible workflow execution service."""

    READ_CHUNK_SIZE = FileOperationConstants.READ_CHUNK_SIZE

    def __init__(self, api_client: InternalAPIClient = None):
        self.api_client = api_client
        self.logger = logger
        self._last_execution_error = None

    def execute_workflow_for_file(
        self,
        file_processing_context: FileProcessingContext,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        is_api: bool = False,
        use_file_history: bool = False,
        workflow_file_execution_id: str = None,
        workflow_logger=None,
    ) -> WorkflowExecutionResult:
        """Execute workflow with clean, linear flow and comprehensive result propagation."""
        start_time = time.time()
        file_hash = file_processing_context.file_hash
        file_name = file_hash.file_name

        # Initialize result tracking variables
        workflow_success = False
        execution_error = None
        tool_instances_data = []
        context_setup_time = start_time
        destination_start_time = start_time
        destination_end_time = start_time

        try:
            logger.info(f"Executing workflow {workflow_id} for file {file_name}")

            # Step 0: Check if file execution is already completed (resume capability)
            if workflow_file_execution_id:
                try:
                    tracker = FileExecutionStatusTracker()
                    existing_data = tracker.get_data(
                        execution_id, workflow_file_execution_id
                    )

                    if (
                        existing_data
                        and existing_data.stage_status.stage
                        == FileExecutionStage.COMPLETED
                    ):
                        if (
                            existing_data.stage_status.status
                            == FileExecutionStageStatus.SUCCESS
                        ):
                            logger.info(
                                f"File {file_name} already completed successfully, skipping processing"
                            )
                            # Return existing successful result
                            return WorkflowExecutionResult(
                                file_name=file_name,
                                file_execution_id=workflow_file_execution_id,
                                success=True,
                                error=None,
                                result="Already completed",
                                metadata=WorkflowExecutionMetadata(
                                    total_execution_time=0,
                                    workflow_success=True,
                                    execution_error=None,
                                    tool_instances_data=[],
                                    destination_result=FinalOutputResult(
                                        output="Already completed",
                                        metadata={},
                                        error=None,
                                        processed=True,
                                    ),
                                ),
                                execution_time=0,
                            )
                except Exception as tracker_error:
                    logger.warning(
                        f"Failed to check execution tracker for {file_name}: {tracker_error}"
                    )
                    # Continue with normal execution if tracker check fails

            # Step 1: Setup & Validation
            if not self.api_client:
                raise ValueError("API client required for workflow execution")

            execution_context, tool_instances_data = self._get_workflow_execution_context(
                execution_id, workflow_id, organization_id
            )

            workflow_context = self._get_workflow(workflow_id, organization_id)

            context_setup_time = time.time()
            logger.info(
                f"TIMING: Workflow context setup COMPLETED for {file_name} at {context_setup_time:.6f} (took {context_setup_time - start_time:.3f}s)"
            )

            if not tool_instances_data:
                raise ValueError(f"No tool instances found for workflow {workflow_id}")

            # Initialize file execution tracker with complete metadata
            if workflow_file_execution_id:
                self._initialize_file_execution_tracker(
                    execution_id=execution_id,
                    file_execution_id=workflow_file_execution_id,
                    organization_id=organization_id,
                    file_hash=file_hash,
                )
            pipeline_id = execution_context.get("execution", {}).get("pipeline_id")
            # Step 2: Execute Workflow
            execution_service = self._create_worker_execution_service(
                organization_id=organization_id,
                workflow_id=workflow_id,
                tool_instances_data=tool_instances_data,
                execution_id=execution_id,
                file_execution_id=workflow_file_execution_id,
                is_api=is_api,
                workflow_logger=workflow_logger,
                pipeline_id=pipeline_id,
            )

            workflow_success = self._execute_workflow_with_service(
                execution_service=execution_service,
                file_processing_context=file_processing_context,
                file_name=file_name,
                workflow_file_execution_id=workflow_file_execution_id,
                execution_id=execution_id,
                workflow_id=workflow_id,
            )

            if not workflow_success:
                execution_error = (
                    self._last_execution_error or "Workflow execution failed"
                )
        except Exception as e:
            logger.error(f"Workflow setup failed for {file_name}: {e}", exc_info=True)
            execution_error = str(e)
            workflow_success = False

        # Step 3: Process Output - Let destination handle EVERYTHING
        # This includes:
        # - Extracting tool results via get_tool_execution_result_from_execution_context
        # - Caching API results
        # - Writing to filesystem/database
        # - Routing to manual review
        # - Creating file history
        destination_result = None
        destination_start_time = time.time()
        logger.info(
            f"TIMING: Destination processing START for {file_name} at {destination_start_time:.6f}"
        )

        try:
            destination_result = self._handle_destination_processing(
                file_processing_context=file_processing_context,
                workflow=workflow_context,
                workflow_id=workflow_id,
                execution_id=execution_id,
                is_success=workflow_success,
                workflow_file_execution_id=workflow_file_execution_id,
                organization_id=organization_id,
                workflow_logger=workflow_logger,
                use_file_history=use_file_history,
                is_api=is_api,
                execution_error=execution_error,
            )
            logger.info(f"Destination processing completed for {file_name}")

            # Mark destination processing as successful - only if workflow succeeded AND no destination errors AND actually processed (not duplicate)
            if (
                workflow_file_execution_id
                and workflow_success
                and destination_result
                and not destination_result.error
                and getattr(
                    destination_result, "processed", True
                )  # Only update if actually processed (not a duplicate skip)
            ):
                try:
                    tracker = FileExecutionStatusTracker()
                    tracker.update_stage_status(
                        execution_id=execution_id,
                        file_execution_id=workflow_file_execution_id,
                        stage_status=FileExecutionStageData(
                            stage=FileExecutionStage.DESTINATION_PROCESSING,
                            status=FileExecutionStageStatus.SUCCESS,
                        ),
                    )
                    logger.info(
                        f"Marked destination processing as successful for {file_name}"
                    )

                except Exception as tracker_error:
                    logger.warning(
                        f"Failed to mark destination processing success: {tracker_error}"
                    )

        except Exception as dest_error:
            logger.error(
                f"Destination processing failed for {file_name}: {dest_error}",
                exc_info=True,
            )
            destination_result = FinalOutputResult(
                output=None, metadata=None, error=str(dest_error)
            )
        finally:
            destination_end_time = time.time()
            logger.info(
                f"TIMING: Destination processing END for {file_name} at {destination_end_time:.6f} (took {destination_end_time - destination_start_time:.3f}s)"
            )

        # Step 4: Build Final Result
        final_time = time.time()
        execution_time = final_time - start_time

        # Build result first
        result = self._build_final_result(
            workflow_file_execution_id=workflow_file_execution_id,
            file_name=file_name,
            file_hash=file_hash,
            workflow_success=workflow_success,
            destination_result=destination_result,
            execution_error=execution_error,
            execution_time=execution_time,
            workflow_id=workflow_id,
            execution_id=execution_id,
            tool_count=len(tool_instances_data),
        )

        # FINAL STEP: Update METADATA.json with correct execution timing
        # This must be done AFTER all tool execution and destination processing
        # to ensure our timing is not overwritten by tool metadata updates
        try:
            file_handler = ExecutionFileHandler(
                workflow_id=workflow_id,
                execution_id=execution_id,
                organization_id=organization_id,
                file_execution_id=workflow_file_execution_id,
            )
            logger.info(
                f"TIMING: Applying FINAL metadata update with execution time: {execution_time:.3f}s"
            )
            file_handler.update_execution_timing(execution_time)

        except Exception as timing_error:
            logger.warning(
                f"Failed to update execution timing in metadata: {timing_error}"
            )
            # Continue - timing update failure shouldn't stop execution

        # Track final completion stage
        if workflow_file_execution_id:
            try:
                tracker = FileExecutionStatusTracker()
                overall_success = workflow_success and (
                    destination_result
                    and not destination_result.error
                    and getattr(destination_result, "processed", True)
                )

                # Check if this was a duplicate skip (processed=False)
                # For duplicate skips, we don't update any stages to avoid interfering with active worker
                is_duplicate_skip = destination_result and not getattr(
                    destination_result, "processed", True
                )

                # Stage flow: DESTINATION_PROCESSING(2) → FINALIZATION(3) → COMPLETED(4)
                if overall_success:
                    # Mark finalization as successful
                    tracker.update_stage_status(
                        execution_id=execution_id,
                        file_execution_id=workflow_file_execution_id,
                        stage_status=FileExecutionStageData(
                            stage=FileExecutionStage.FINALIZATION,
                            status=FileExecutionStageStatus.SUCCESS,
                        ),
                    )
                    logger.info(f"Marked finalization as successful for {file_name}")

                    # Use shorter TTL for COMPLETED stage to optimize Redis memory
                    completed_ttl = int(
                        os.environ.get(
                            "FILE_EXECUTION_TRACKER_COMPLETED_TTL_IN_SECOND", 300
                        )
                    )
                    tracker.update_stage_status(
                        execution_id=execution_id,
                        file_execution_id=workflow_file_execution_id,
                        stage_status=FileExecutionStageData(
                            stage=FileExecutionStage.COMPLETED,
                            status=FileExecutionStageStatus.SUCCESS,
                        ),
                        ttl_in_second=completed_ttl,
                    )
                    logger.info(f"Tracked successful completion for {file_name}")
                elif not is_duplicate_skip:
                    # Track failure on finalization stage (only for actual failures, not duplicate skips)
                    error_msg = execution_error or (
                        destination_result.error
                        if destination_result
                        else "Unknown error"
                    )
                    tracker.update_stage_status(
                        execution_id=execution_id,
                        file_execution_id=workflow_file_execution_id,
                        stage_status=FileExecutionStageData(
                            stage=FileExecutionStage.FINALIZATION,
                            status=FileExecutionStageStatus.FAILED,
                            error=error_msg,
                        ),
                    )
                    logger.info(f"Tracked failed execution for {file_name}: {error_msg}")
                else:
                    # Duplicate skip - don't update any stages to avoid interfering with active worker
                    logger.info(
                        f"Skipping finalization stage update for '{file_name}' - duplicate detected, stages managed by active worker"
                    )

                # Clean up tool execution tracker only if we actually processed (not duplicate)
                # For duplicate skips, the active worker will clean up its own tracker when it finishes
                if not is_duplicate_skip:
                    self._cleanup_tool_execution_tracker(
                        execution_id=execution_id,
                        file_execution_id=workflow_file_execution_id,
                    )
                else:
                    logger.info(
                        f"Skipping tool execution tracker cleanup for '{file_name}' - duplicate detected, tracker managed by active worker"
                    )

            except Exception as tracker_error:
                logger.warning(f"Failed to track final completion stage: {tracker_error}")

        return result

    def _initialize_file_execution_tracker(
        self,
        execution_id: str,
        file_execution_id: str,
        organization_id: str,
        file_hash: FileHashData,
    ) -> None:
        """Initialize file execution tracker with complete metadata.

        Matches Django backend initialization pattern with full FileExecutionData.
        """
        try:
            tracker = FileExecutionStatusTracker()

            # Check if tracker already exists (resume scenario)
            if tracker.exists(execution_id, file_execution_id):
                logger.info(
                    f"File execution tracker already exists for execution_id: {execution_id}, "
                    f"file_execution_id: {file_execution_id}"
                )
                return

            # Create initial stage data
            file_execution_stage_data = FileExecutionStageData(
                stage=FileExecutionStage.INITIALIZATION,
                status=FileExecutionStageStatus.IN_PROGRESS,
            )

            # Create complete FileExecutionData with metadata
            file_execution_data = FileExecutionData(
                execution_id=str(execution_id),
                file_execution_id=str(file_execution_id),
                organization_id=str(organization_id),
                stage_status=file_execution_stage_data,
                status_history=[],
                file_hash=file_hash.to_serialized_json(),  # Match Django backend serialization format
            )

            # Initialize tracker with complete data
            tracker.set_data(file_execution_data)
            logger.info(
                f"Initialized file execution tracker for execution_id: {execution_id}, "
                f"file_execution_id: {file_execution_id}"
            )

        except Exception as e:
            # Non-critical - log and continue
            logger.warning(
                f"Failed to initialize file execution tracker for {execution_id}/{file_execution_id}: {e}"
            )

    def _cleanup_tool_execution_tracker(
        self,
        execution_id: str,
        file_execution_id: str,
    ) -> None:
        """Clean up tool execution tracker after file processing completes.

        Matches Django backend cleanup pattern to prevent Redis memory leaks.
        """
        try:
            tracker = ToolExecutionTracker()
            tool_execution_data = ToolExecutionData(
                execution_id=execution_id,
                file_execution_id=file_execution_id,
            )
            tracker.delete_status(tool_execution_data=tool_execution_data)
            logger.info(
                f"Deleted tool execution tracker for execution_id: {execution_id}, "
                f"file_execution_id: {file_execution_id}"
            )
        except Exception as e:
            # Non-critical - log and continue
            logger.warning(
                f"Failed to cleanup tool execution tracker for {execution_id}/{file_execution_id}: {e}"
            )

    def _get_workflow_execution_context(
        self, execution_id: str, workflow_id: str, organization_id: str
    ) -> tuple[dict, list]:
        """Get workflow execution context and tool instances."""
        execution_response = self.api_client.get_workflow_execution(execution_id)
        if not execution_response.success:
            raise Exception(
                f"Failed to get workflow execution: {execution_response.error}"
            )

        tool_instances_response = self.api_client.get_tool_instances_by_workflow(
            workflow_id=workflow_id,
            organization_id=organization_id,
        )

        return execution_response.data, tool_instances_response.tool_instances

    def _get_workflow(
        self, workflow_id: str, organization_id: str
    ) -> WorkflowDefinitionResponseData:
        """Get workflow definition including workflow_type."""
        return self.api_client.get_workflow(workflow_id, organization_id)

    def _build_final_result(
        self,
        workflow_file_execution_id: str,
        file_name: str,
        file_hash: FileHashData,
        workflow_success: bool,
        destination_result: FinalOutputResult,
        execution_error: str,
        execution_time: float,
        workflow_id: str,
        execution_id: str,
        tool_count: int,
    ) -> WorkflowExecutionResult:
        """Build standardized result using DTO."""
        # Determine overall success
        overall_success = workflow_success and (
            destination_result and not destination_result.error
        )

        # Consolidate errors
        final_error = None
        if execution_error and destination_result and destination_result.error:
            final_error = (
                f"Execution: {execution_error}; Destination: {destination_result.error}"
            )
        elif execution_error:
            final_error = execution_error
        elif destination_result and destination_result.error:
            final_error = destination_result.error

        # Build metadata
        # CRITICAL: Check destination_result.processed (not just existence) to detect duplicate skips
        # destination_result.processed=False means duplicate was detected and skipped
        metadata = WorkflowExecutionMetadata(
            workflow_id=workflow_id,
            execution_id=execution_id,
            execution_time=execution_time,
            tool_count=tool_count,
            workflow_executed=workflow_success,
            destination_processed=(
                getattr(destination_result, "processed", True)
                if destination_result
                else False
            ),
            destination_error=destination_result.error if destination_result else None,
        )

        # Return structured result
        return WorkflowExecutionResult(
            file_execution_id=workflow_file_execution_id,
            file_name=file_name,
            success=overall_success,
            error=final_error,
            result=destination_result.output if destination_result else None,
            source_hash=file_hash.file_hash,
            metadata=metadata,
            destination_output=destination_result.output if destination_result else None,
        )

    def _create_execution_result(
        self,
        workflow_file_execution_id: str,
        file_name: str,
        file_data: dict[str, Any],
        success: bool,
        result: Any = None,
        error: str = None,
        metadata: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Create standardized execution result structure for both success and error cases."""
        return {
            "file_execution_id": workflow_file_execution_id,
            "file": file_name,
            "result": result,
            "success": success,
            "error": error,
            "metadata": metadata,
            "source_hash": file_data.get("file_hash"),
        }

    def _create_worker_execution_service(
        self,
        organization_id: str,
        workflow_id: str,
        tool_instances_data: list[dict[str, Any]],
        execution_id: str,
        file_execution_id: str,
        is_api: bool = False,
        workflow_logger: Any | None = None,
        pipeline_id: str | None = None,
    ) -> WorkflowExecutionService:
        """Create WorkflowExecutionService following backend pattern."""
        # Convert tool instances data to ToolInstance DTOs
        tool_instances = []
        for tool_data in tool_instances_data:
            try:
                # Get tool information from the backend via API
                # This is necessary because workers can't access Django models for Prompt Studio tools
                tool_info = None
                tool_id = tool_data.get("tool_id")
                if tool_id and self.api_client:
                    try:
                        tool_info_response = self.api_client.get_tool_by_id(tool_id)
                        tool_info = tool_info_response.get("tool", {})
                        logger.info(f"Successfully fetched tool info for {tool_id}")
                    except Exception as tool_fetch_error:
                        logger.warning(
                            f"Could not fetch tool info for {tool_id}: {tool_fetch_error}"
                        )

                # Use tool info if available, otherwise fail execution
                if (
                    tool_info
                    and tool_info.get("properties")
                    and tool_info.get("image_name")
                ):
                    properties = tool_info.get("properties", {})
                    image_name = tool_info.get("image_name")
                    image_tag = tool_info.get("image_tag", "latest")
                    logger.info(f"Successfully loaded tool properties for {tool_id}")
                else:
                    # If we can't get valid tool data, fail the execution
                    error_msg = f"Cannot execute workflow: Invalid or missing tool data for {tool_id}. Tool registry may be unavailable or tool not found."
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                tool_instance = ToolInstance(
                    id=tool_data.get("id"),
                    tool_id=tool_data.get("tool_id"),
                    step=tool_data.get("step", 1),
                    workflow=workflow_id,
                    metadata=tool_data.get("metadata", {}),
                    properties=properties,
                    image_name=image_name,
                    image_tag=image_tag,
                )
                tool_instances.append(tool_instance)
            except Exception as tool_error:
                logger.warning(
                    f"Failed to create tool instance from data {tool_data}: {tool_error}"
                )
                continue

        if not tool_instances:
            raise ValueError("Failed to create any valid tool instances")

        # Create WorkflowDto
        workflow_dto = WorkflowDto(id=workflow_id)

        # Get platform service API key from backend API
        platform_service_api_key = self._get_platform_service_api_key(organization_id)

        # Initialize WorkflowExecutionService
        execution_service = WorkflowExecutionService(
            organization_id=organization_id,
            workflow_id=workflow_id,
            workflow=workflow_dto,
            tool_instances=tool_instances,
            platform_service_api_key=platform_service_api_key,
            ignore_processed_entities=False,
            file_execution_id=file_execution_id,
        )

        # Set up messaging channel for logs
        # Get messaging channel from workflow_logger if available
        # This ensures consistency with WorkflowLogger which uses:
        # log_events_id (session) for UI workflows or pipeline_id for scheduled/API
        if workflow_logger and hasattr(workflow_logger, "messaging_channel"):
            messaging_channel = workflow_logger.messaging_channel
            logger.info(
                f"Using workflow_logger messaging channel: {messaging_channel} "
                f"for execution {execution_id}, file {file_execution_id}"
            )
        else:
            # Fallback: use execution_id if no workflow_logger available
            # This shouldn't normally happen but provides safety
            messaging_channel = str(pipeline_id) if pipeline_id else str(execution_id)
            logger.warning(
                f"No workflow_logger available, using pipeline_id or execution_id as messaging channel: {messaging_channel} "
                f"for file {file_execution_id}"
            )

        execution_service.set_messaging_channel(messaging_channel)

        return execution_service

    def _execute_workflow_with_service(
        self,
        execution_service: WorkflowExecutionService,
        file_processing_context: FileProcessingContext,
        file_name: str,
        workflow_file_execution_id: str,
        execution_id: str,
        workflow_id: str,
    ) -> bool:
        """Execute workflow using WorkflowExecutionService following backend pattern."""
        try:
            # Step 1: Compile workflow
            if not self._compile_workflow(execution_service, execution_id, file_name):
                return False

            # Step 2: Prepare input file and metadata
            self._prepare_workflow_input_file(
                execution_service=execution_service,
                file_processing_context=file_processing_context,
                workflow_id=workflow_id,
                execution_id=execution_id,
                workflow_file_execution_id=workflow_file_execution_id,
            )

            # Step 3: Build and execute workflow
            self._build_and_execute_workflow(execution_service, file_name)

            return True

        except Exception as e:
            logger.error(
                f"Tool execution failed for file {file_name}: {str(e)}", exc_info=True
            )
            self._last_execution_error = str(e)
            return False

    def _compile_workflow(
        self,
        execution_service: WorkflowExecutionService,
        execution_id: str,
        file_name: str,
    ) -> bool:
        """Compile the workflow and check for errors."""
        compilation_result = execution_service.compile_workflow(execution_id)
        if not compilation_result.get("success"):
            error_msg = f"Workflow compilation failed: {compilation_result.get('problems', ['Unknown error'])}"
            logger.error(error_msg)
            self._last_execution_error = error_msg
            return False

        logger.info(f"Workflow compiled successfully for file {file_name}")
        return True

    def _prepare_workflow_input_file(
        self,
        execution_service: WorkflowExecutionService,
        file_processing_context: FileProcessingContext,
        workflow_id: str,
        execution_id: str,
        workflow_file_execution_id: str,
    ) -> str:
        """Prepare input file for workflow execution and return computed hash."""
        file_handler = execution_service.file_handler

        try:
            # Get file information from file_data parameter
            file_path = file_processing_context.file_hash.file_path
            source_connection_type = (
                file_processing_context.file_hash.source_connection_type
            )
            connector_metadata = file_processing_context.file_hash.connector_metadata
            file_data = file_processing_context.file_data
            # Get source configuration
            source_config = self._get_source_config(workflow_id, execution_id)
            source_connector_id, source_config_connector_settings = (
                self._extract_source_connector_details(source_config)
            )

            # Get target paths
            infile_path = file_handler.infile
            source_file_path = file_handler.source_file

            if not self._validate_file_paths(infile_path, source_file_path, file_path):
                raise ValueError(
                    f"Missing required file paths: infile_path={infile_path}, "
                    f"source_file_path={source_file_path}, file_path={file_path}"
                )

            logger.info(f"Copying source file {file_path} to execution directory")

            # Determine connection type and copy file
            connection_type = self._determine_connection_type(source_connection_type)

            if connection_type.is_api:
                computed_hash = self._copy_api_file(
                    file_path=file_path,
                    infile_path=infile_path,
                    source_file_path=source_file_path,
                    file_processing_context=file_processing_context,
                )

            else:
                computed_hash = self._copy_filesystem_file(
                    file_path=file_path,
                    infile_path=infile_path,
                    source_file_path=source_file_path,
                    file_processing_context=file_processing_context,
                    source_connector_id=source_connector_id,
                    source_config_connector_settings=source_config_connector_settings,
                    connector_metadata=connector_metadata,
                )

            # Create initial METADATA.json file
            # Extract tag names from workflow execution context
            tag_names = []
            workflow_execution = file_processing_context.workflow_execution
            if workflow_execution and workflow_execution.get("tags"):
                tag_names = [tag["name"] for tag in workflow_execution["tags"]]

            file_handler.add_metadata_to_volume(
                input_file_path=file_path,
                file_execution_id=workflow_file_execution_id,
                source_hash=computed_hash,
                tags=tag_names,  # Pass actual tag names from execution
                llm_profile_id=file_data.llm_profile_id,
                custom_data=file_data.custom_data,
            )
            logger.info(f"Initial metadata file created for {file_path}")

            return computed_hash

        except Exception as file_prep_error:
            logger.error(f"Failed to prepare input file and metadata: {file_prep_error}")
            raise file_prep_error

    def _build_and_execute_workflow(
        self, execution_service: WorkflowExecutionService, file_name: str
    ) -> None:
        """Build and execute the workflow."""
        # Build workflow
        execution_service.build_workflow()
        logger.info(f"Workflow built successfully for file {file_name}")

        # Execute workflow
        from unstract.workflow_execution.enums import ExecutionType

        execution_service.execute_workflow(ExecutionType.COMPLETE)
        logger.info(f"Workflow executed successfully for file {file_name}")

    def _extract_source_connector_details(
        self, source_config: dict[str, Any] | None
    ) -> tuple[str | None, dict[str, Any]]:
        """Extract source connector ID and settings from config."""
        if source_config:
            source_connector_id = source_config.get("connector_id")
            source_config_connector_settings = source_config.get("connector_settings", {})
            logger.info(f"Retrieved source config - connector_id: {source_connector_id}")
            return source_connector_id, source_config_connector_settings
        return None, {}

    def _validate_file_paths(
        self, infile_path: str | None, source_file_path: str | None, file_path: str | None
    ) -> bool:
        """Validate that all required file paths are present."""
        return bool(infile_path and source_file_path and file_path)

    def _determine_connection_type(self, source_connection_type: str):
        """Determine the connection type from string."""
        from unstract.connectors import ConnectionType

        try:
            return ConnectionType.from_string(source_connection_type)
        except ValueError:
            logger.warning(
                f"Invalid source_connection_type: {source_connection_type}, defaulting to FILESYSTEM"
            )
            return ConnectionType.FILESYSTEM

    def _copy_api_file(
        self,
        file_path: str,
        infile_path: str,
        source_file_path: str,
        file_processing_context: FileProcessingContext,
    ) -> str:
        """Copy file from API storage to workflow execution directory using chunked reading."""
        import hashlib

        from unstract.filesystem import FileStorageType, FileSystem

        logger.info(f"Handling API file copy from {file_path} to execution directory")

        # Get file systems
        api_file_system = FileSystem(FileStorageType.API_EXECUTION)
        api_file_storage = api_file_system.get_file_storage()

        workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        workflow_file_storage = workflow_file_system.get_file_storage()

        # Copy file in chunks
        file_content_hash = hashlib.sha256()
        total_bytes_copied = 0
        seek_position = 0  # Track position for sequential reads

        logger.info(f"Starting chunked file copy from API storage for {file_path}")

        # Read and write in chunks
        while chunk := api_file_storage.read(
            path=file_path,
            mode="rb",
            seek_position=seek_position,
            length=self.READ_CHUNK_SIZE,
        ):
            file_content_hash.update(chunk)
            total_bytes_copied += len(chunk)
            seek_position += len(chunk)

            # Write chunk to both INFILE and SOURCE
            workflow_file_storage.write(path=infile_path, mode="ab", data=chunk)
            workflow_file_storage.write(path=source_file_path, mode="ab", data=chunk)

        # Handle empty files - raise exception instead of creating placeholders
        if total_bytes_copied == 0:
            raise EmptyFileError(file_path)
        else:
            computed_hash = file_content_hash.hexdigest()
            logger.info(
                f"Successfully copied {total_bytes_copied} bytes from API storage with hash: {computed_hash}"
            )

        # Store computed hash in file_data for file history
        file_processing_context.file_hash.file_hash = computed_hash
        return computed_hash

    def _copy_filesystem_file(
        self,
        file_path: str,
        infile_path: str,
        source_file_path: str,
        file_processing_context: FileProcessingContext,
        source_connector_id: str | None,
        source_config_connector_settings: dict[str, Any],
        connector_metadata: dict[str, Any],
    ) -> str:
        """Copy file from filesystem connector to workflow execution directory."""
        import hashlib

        from unstract.connectors.constants import Common
        from unstract.connectors.filesystems import connectors
        from unstract.filesystem import FileStorageType, FileSystem

        # Get workflow file storage
        workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
        workflow_file_storage = workflow_file_system.get_file_storage()

        # Determine which connector to use
        connector_id_to_use, connector_settings_to_use = self._resolve_connector_config(
            source_connector_id=source_connector_id,
            source_config_connector_settings=source_config_connector_settings,
            connector_metadata=connector_metadata,
            file_processing_context=file_processing_context,
        )

        if not connector_id_to_use:
            available_connectors = list(connectors.keys())
            raise ValueError(
                f"No connector_id provided for filesystem connection type. "
                f"Available connectors: {available_connectors}"
            )

        if connector_id_to_use not in connectors:
            available_connectors = list(connectors.keys())
            raise ValueError(
                f"Connector not found in registry: {connector_id_to_use}. "
                f"Available connectors: {available_connectors}"
            )

        logger.info(f"Using connector: {connector_id_to_use}")

        # Get source filesystem
        connector_class = connectors[connector_id_to_use][Common.METADATA][
            Common.CONNECTOR
        ]
        source_connector = connector_class(connector_settings_to_use)
        source_fs = source_connector.get_fsspec_fs()

        # Copy file in chunks
        file_content_hash = hashlib.sha256()
        total_bytes_copied = 0
        first_chunk = True

        logger.info(f"Starting chunked file copy from {file_path} to execution directory")

        with source_fs.open(file_path, "rb") as source_file:
            while chunk := source_file.read(self.READ_CHUNK_SIZE):
                # MIME type detection and validation on first chunk
                if first_chunk:
                    mime_type = magic.from_buffer(chunk, mime=True)
                    logger.info(f"Detected MIME type: {mime_type} for file {file_path}")

                    if not AllowedFileTypes.is_allowed(mime_type):
                        raise UnsupportedMimeTypeError(
                            f"Unsupported MIME type '{mime_type}' for file '{file_path}'"
                        )
                    first_chunk = False

                file_content_hash.update(chunk)
                total_bytes_copied += len(chunk)

                # Write chunk to both INFILE and SOURCE
                workflow_file_storage.write(path=infile_path, mode="ab", data=chunk)
                workflow_file_storage.write(path=source_file_path, mode="ab", data=chunk)

        # Handle empty files - raise exception instead of using _handle_empty_file
        if total_bytes_copied == 0:
            raise EmptyFileError(file_path)
        else:
            computed_hash = file_content_hash.hexdigest()
            logger.info(
                f"Successfully copied {total_bytes_copied} bytes with hash: {computed_hash}"
            )

        # Store computed hash in file_data for file history
        file_processing_context.file_hash.file_hash = computed_hash
        return computed_hash

    def _resolve_connector_config(
        self,
        source_connector_id: str | None,
        source_config_connector_settings: dict[str, Any],
        connector_metadata: dict[str, Any],
        file_processing_context: FileProcessingContext,
    ) -> tuple[str | None, dict[str, Any]]:
        """Resolve which connector configuration to use."""
        # Prefer source config (has auth tokens)
        if source_connector_id and source_config_connector_settings:
            logger.info(f"Using connector from source config: {source_connector_id}")
            return source_connector_id, source_config_connector_settings

        # Fall back to file metadata
        if connector_metadata and "connector_id" in connector_metadata:
            connector_id = connector_metadata["connector_id"]
            logger.warning(
                f"Using connector_id from file metadata (may lack auth): {connector_id}"
            )
            return connector_id, connector_metadata

        # Fall back to file_data
        if file_processing_context.file_hash.connector_id:
            connector_id = file_processing_context.file_hash.connector_id
            connector_settings = file_processing_context.file_hash.connector_settings
            logger.warning(
                f"Using connector_id from file_data (may lack auth): {connector_id}"
            )
            return connector_id, connector_settings

        logger.error("No connector_id found in any configuration source")
        return None, {}

    def _handle_destination_processing(
        self,
        file_processing_context: FileProcessingContext,
        workflow: WorkflowDefinitionResponseData,
        workflow_id: str,
        execution_id: str,
        is_success: bool,
        workflow_file_execution_id: str,
        organization_id: str,
        workflow_logger=None,
        use_file_history: bool = False,
        is_api: bool = False,
        execution_error: str | None = None,
    ) -> FinalOutputResult:
        """Handle destination processing for ETL/TASK workflows following backend pattern.

        This matches the exact pattern from backend/workflow_manager/workflow_v2/file_execution_tasks.py
        _process_final_output method.
        """
        try:
            file_hash = file_processing_context.file_hash
            file_data = file_processing_context.file_data
            logger.info(
                f"Starting destination processing for file {file_hash.file_name} in workflow {workflow_id}"
            )
            if not workflow.destination_config:
                logger.warning(
                    f"No destination configuration found for workflow {workflow_id}"
                )
                raise NotFoundDestinationConfiguration(
                    "No destination configuration found"
                )

            # Get source configuration to populate source connector settings
            if not workflow.source_config:
                logger.warning(
                    f"No source configuration found for workflow {workflow_id}"
                )
                raise NotFoundSourceConfiguration("No source configuration found")

            # Get destination configuration via API
            destination_config = workflow.destination_config.to_dict()

            # Add source connector information to destination config for manual review
            source_connector_info = (
                self._extract_source_connector_info_to_update_destination(
                    source_config=workflow.source_config
                )
            )
            if source_connector_info:
                destination_config.update(source_connector_info)
                logger.info(
                    f"Added source connector info to destination config: {source_connector_info.get('source_connector_id', 'none')}"
                )
            source_data = {
                "source_connection_type": workflow.source_config.connection_type,
            }
            destination_config.update(source_data)

            source_connection_type = workflow.source_config.connection_type

            # Add HITL queue name from file_data if present (for API deployments)
            hitl_queue_name = file_data.hitl_queue_name
            destination_config["use_file_history"] = use_file_history
            destination_config["file_execution_id"] = workflow_file_execution_id
            if hitl_queue_name:
                destination_config["hitl_queue_name"] = hitl_queue_name
                logger.info(
                    f"Added HITL queue name to destination config: {hitl_queue_name}"
                )
            else:
                logger.info(
                    "No hitl_queue_name found in file_data, proceeding with normal processing"
                )

            # Import destination connector

            # Create destination config object (matching backend DestinationConnector.from_config)
            dest_config = DestinationConfig.from_dict(destination_config)
            logger.info(
                f"Created destination config: {dest_config.connection_type} with source connector: {dest_config.source_connector_id}"
            )
            # Create destination connector (matching backend pattern)
            destination = WorkerDestinationConnector.from_config(
                workflow_logger, dest_config
            )

            # Process final output through destination (matching backend exactly)
            output_result = None
            processing_error = None  # No processing error since workflow succeeded

            try:
                # CRITICAL: Log file destination routing decision
                if file_hash.is_manualreview_required:
                    logger.info(
                        f"🔄 File {file_hash.file_name} marked for MANUAL REVIEW - sending to queue"
                    )
                else:
                    destination_display = destination._get_destination_display_name()
                    logger.info(
                        f"📤 File {file_hash.file_name} marked for DESTINATION processing - sending to {destination_display}"
                    )

                # Process final output through destination (exact backend signature + workers-specific params)
                handle_output_result = destination.handle_output(
                    is_success=is_success,
                    file_hash=file_hash,
                    # file_history=file_history,
                    workflow={"id": workflow_id},  # Minimal workflow object like backend
                    file_execution_id=workflow_file_execution_id,
                    # Workers-specific parameters (needed for API-based operation)
                    api_client=self.api_client,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    organization_id=organization_id,
                    execution_error=execution_error,
                )

                # Check if handle_output returned None (duplicate detected)
                if handle_output_result is None:
                    # Enhanced debug log with full context for internal debugging
                    logger.info(
                        f"DUPLICATE SKIP: File '{file_hash.file_name}' duplicate detected at destination phase. "
                        f"execution_id={execution_id}, file_execution_id={workflow_file_execution_id}, "
                        f"workflow_id={workflow_id}. "
                        f"Returning FinalOutputResult with processed=False, no file history will be created. "
                        f"This is an internal race condition, not an error."
                    )
                    # Return special result to indicate duplicate (not an error, not processed)
                    return FinalOutputResult(
                        output=None,
                        metadata=None,
                        error=None,  # Not an error - just a duplicate skip
                        processed=False,  # Indicates this was skipped due to duplicate
                    )

                output_result = handle_output_result.output
                metadata = handle_output_result.metadata
                source_connection_type = workflow.source_config.connection_type
            except Exception as dest_error:
                logger.error(
                    f"Destination processing failed in _handle_destination_processing: {dest_error}",
                    exc_info=True,
                )
                processing_error = str(dest_error)
                output_result = None

            # Handle metadata for API workflows (matching backend pattern)
            execution_metadata = None
            if self._should_create_file_history(
                destination=destination,
                # file_history=file_history,
                output_result=output_result,
                processing_error=processing_error,
            ):
                # Create file history entry via API client
                logger.info(f"Creating file history entry for {file_hash.file_name}")

                # Serialize result and metadata for API
                import json

                result_json = ""
                if output_result and destination.is_api:
                    try:
                        result_json = (
                            json.dumps(output_result)
                            if isinstance(output_result, (dict, list))
                            else str(output_result)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to serialize result: {e}")
                        result_json = str(output_result)

                # Create file history via API
                file_history_response = self.api_client.create_file_history(
                    file_path=file_hash.file_path if not destination.is_api else None,
                    file_name=file_hash.file_name,
                    source_connection_type=str(source_connection_type),
                    workflow_id=workflow_id,
                    file_hash=file_hash.file_hash,
                    file_size=getattr(file_hash, "file_size", 0),
                    mime_type=getattr(file_hash, "mime_type", ""),
                    result=result_json,
                    metadata=metadata,
                    status="COMPLETED",
                    provider_file_uuid=getattr(file_hash, "provider_file_uuid", None),
                    is_api=destination.is_api,
                )

                if file_history_response.success:
                    logger.info(f"Created file history entry for {file_hash.file_name}")
                else:
                    logger.warning(
                        f"Failed to create file history: {file_history_response.error}"
                    )

            if processing_error:
                logger.error(
                    f"Destination processing failed for file {file_hash.file_name}: {processing_error}"
                )
                # Return error information so the main method can handle it
                return FinalOutputResult(
                    output=None, metadata=None, error=processing_error
                )
            else:
                logger.info(
                    f"Destination processing completed for file {file_hash.file_name}"
                )
            return FinalOutputResult(
                output=output_result,
                metadata=execution_metadata,
                error=self._last_execution_error,
            )

        except Exception as e:
            error_msg = f"Failed to process destination for workflow {workflow_id}: {e}"
            logger.error(error_msg, exc_info=True)
            return FinalOutputResult(output=None, metadata=None, error=error_msg)

    def _should_create_file_history(
        self,
        destination,
        output_result,
        processing_error,
    ) -> bool:
        """Determine if file history should be created.

        File history creation rules:
        - API workflows: Create WITH results only when use_file_history=True
        - ETL/TASK/MANUAL_REVIEW workflows: Always create WITHOUT results (for tracking)
        """
        # Don't create if there is a tool execution error
        if self._last_execution_error:
            return False

        # Don't create if there's a processing error
        if processing_error:
            return False

        # For API workflows, only create if use_file_history is enabled
        if destination.is_api and not destination.use_file_history:
            return False

        # For API workflows, only create if there's a valid output result
        if destination.is_api and not output_result:
            return False

        return True

    def _get_destination_config(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any] | None:
        """Get destination configuration for the workflow via API."""
        try:
            # Get workflow execution context which includes destination config
            execution_response = self.api_client.get_workflow_execution(execution_id)
            if not execution_response.success:
                raise Exception(
                    f"Failed to get execution context: {execution_response.error}"
                )
            execution_context = execution_response.data
            destination_config = execution_context.get("destination_config", {})

            if not destination_config:
                logger.warning(
                    f"No destination config found in execution context for workflow {workflow_id}"
                )
                return None

            logger.info(
                f"Retrieved destination config for workflow {workflow_id}: {destination_config.get('connection_type')}"
            )
            return destination_config

        except Exception as e:
            logger.error(
                f"Failed to get destination config for workflow {workflow_id}: {e}"
            )
            return None

    def _get_source_config(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any] | None:
        """Get source configuration for the workflow via API."""
        try:
            # Get workflow execution context which includes source config
            execution_response = self.api_client.get_workflow_execution(execution_id)
            if not execution_response.success:
                raise Exception(
                    f"Failed to get execution context: {execution_response.error}"
                )
            execution_context = execution_response.data
            source_config = execution_context.get("source_config", {})

            if not source_config:
                logger.warning(
                    f"No source config found in execution context for workflow {workflow_id}"
                )
                return None

            logger.info(
                f"Retrieved source config for workflow {workflow_id}: {source_config.get('type', 'unknown')}"
            )
            return source_config

        except Exception as e:
            logger.error(f"Failed to get source config for workflow {workflow_id}: {e}")
            return None

    def _extract_source_connector_info_to_update_destination(
        self, source_config: WorkflowEndpointConfigData
    ) -> dict[str, Any] | None:
        """Extract source connector information from source config for destination connector use."""
        try:
            # With updated backend, source config now includes connector instance details directly
            connector_instance = source_config.connector_instance
            if not connector_instance:
                logger.warning(
                    f"No connector instance found in source config: {source_config}"
                )
                return None
            connector_id = connector_instance.connector_id
            connector_settings = connector_instance.connector_metadata

            # if connector_id and connector_settings:
            #     logger.info(f"Extracted source connector info: {connector_id}")
            #     return {
            #         "source_connector_id": connector_id,
            #         "source_connector_settings": connector_settings,
            #     }
            # else:
            # Fallback: check in source_settings for older format
            # source_settings = source_config.configuration
            # connector_id = source_settings.get("connector_id")
            # connector_settings = source_settings.get(
            #     "connector_settings"
            # ) or source_settings.get("metadata")

            if connector_id and connector_settings:
                logger.info(
                    f"Extracted source connector info from source_settings: {connector_id}"
                )
                return {
                    "source_connector_id": connector_id,
                    "source_connector_settings": connector_settings,
                }

            logger.debug(
                f"No source connector info found in source config. Available keys: {list(source_config.keys())}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to extract source connector info: {e}")
            return None

    def _get_platform_service_api_key(self, organization_id: str) -> str:
        """Get platform service API key from backend API.

        Args:
            organization_id: Organization ID

        Returns:
            Platform service API key
        """
        try:
            # Call the internal API to get the platform key using X-Organization-ID header
            response = self.api_client._make_request(
                method="GET",
                endpoint="v1/platform-settings/platform-key/",
                organization_id=organization_id,  # This will be passed as X-Organization-ID header
            )

            if response and "platform_key" in response:
                logger.info(
                    f"Successfully retrieved platform key for org {organization_id}"
                )
                return response["platform_key"]
            else:
                logger.error(
                    f"No platform key found for org {organization_id} in API response"
                )
                raise Exception(
                    f"No active platform key found for organization {organization_id}"
                )

        except Exception as e:
            logger.error(
                f"Failed to get platform key from API for org {organization_id}: {e}"
            )
            raise Exception(
                f"Unable to retrieve platform service API key for organization {organization_id}: {e}"
            )
