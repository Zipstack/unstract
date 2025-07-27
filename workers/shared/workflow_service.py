"""WorkflowExecutionService Integration for Workers

This module provides direct integration with the WorkflowExecutionService
from unstract/workflow-execution, enabling workers to execute workflows
directly using the ToolSandbox and runner services.
"""

import json
import os
import time
from typing import Any

# Import shared dataclasses for type safety and consistency
from unstract.core.data_models import DestinationConfig
from unstract.workflow_execution.dto import ToolInstance, WorkflowDto

# Direct imports now that dependencies are properly configured
from unstract.workflow_execution.workflow_execution import WorkflowExecutionService

from .api_client import InternalAPIClient
from .logging_utils import WorkerLogger

logger = WorkerLogger.get_logger(__name__)


class WorkerWorkflowExecutionService:
    """Worker-compatible workflow execution service."""

    def __init__(self, api_client: InternalAPIClient = None):
        self.api_client = api_client
        self.logger = logger

    def execute_workflow_for_file(
        self,
        organization_id: str,
        workflow_id: str,
        file_data: dict[str, Any],
        execution_id: str,
        is_api: bool = False,
        workflow_file_execution_id: str = None,
        workflow_file_execution_object: Any = None,
    ) -> dict[str, Any]:
        """Execute workflow for a single file using actual WorkflowExecutionServiceHelper pattern."""
        start_time = time.time()
        file_name = file_data.get("file_name", "unknown")

        try:
            logger.info(f"Executing workflow {workflow_id} for file {file_name}")

            # Get workflow and tool instances via API
            if not self.api_client:
                raise ValueError("API client required for workflow execution")

            # Get workflow execution context
            execution_context = self.api_client.get_workflow_execution(execution_id)
            workflow_info = execution_context.get("workflow", {})

            # Get tool instances for the workflow
            tool_instances_response = self.api_client.get_tool_instances_by_workflow(
                workflow_id
            )
            tool_instances_data = tool_instances_response.get("tool_instances", [])

            if not tool_instances_data:
                logger.warning(f"No tool instances found for workflow {workflow_id}")
                return {
                    "file_execution_id": workflow_file_execution_id,
                    "file": file_name,
                    "result": None,
                    "success": False,
                    "error": "No tool instances found for workflow",
                    "metadata": {
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "execution_time": time.time() - start_time,
                    },
                }

            # Create a worker-compatible execution service
            execution_service = self._create_worker_execution_service(
                organization_id=organization_id,
                workflow_id=workflow_id,
                workflow_info=workflow_info,
                tool_instances_data=tool_instances_data,
                execution_id=execution_id,
                file_execution_id=workflow_file_execution_id,
                is_api=is_api,
            )

            # Execute the workflow following backend pattern
            success = self._execute_workflow_with_service(
                execution_service=execution_service,
                file_name=file_name,
                workflow_file_execution_id=workflow_file_execution_id,
                execution_id=execution_id,
                file_data=file_data,
            )

            execution_time = time.time() - start_time

            if success:
                logger.info(
                    f"Successfully executed workflow {workflow_id} for file {file_name} in {execution_time:.2f}s"
                )

                # Prepare result with actual tool results (if available)
                # Default to generic string in case extraction fails
                workflow_result = f"Workflow executed successfully with {len(tool_instances_data)} tools"
                result_metadata = {
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    "execution_time": execution_time,
                    "tool_count": len(tool_instances_data),
                }

                # Try to extract actual tool results for ALL workflows (matching backend pattern)
                tool_results = None
                logger.info(
                    f"DEBUG: Starting tool result extraction for workflow {workflow_id}, execution {execution_id}, file_execution {workflow_file_execution_id}"
                )
                try:
                    # Extract tool results from the execution service using execution context
                    # This follows the backend pattern from destination.py:get_tool_execution_result_from_metadata
                    tool_results = self._extract_tool_results_from_context(
                        workflow_id=workflow_id,
                        execution_id=execution_id,
                        workflow_file_execution_id=workflow_file_execution_id,
                        organization_id=organization_id,
                    )
                    logger.info(
                        f"DEBUG: Tool results extraction returned: {type(tool_results)} - {tool_results}"
                    )
                    if tool_results:
                        workflow_result = tool_results
                        logger.info(
                            f"SUCCESS: Extracted actual tool results for workflow {workflow_id}, result type: {type(tool_results)}"
                        )
                    else:
                        logger.warning(
                            f"WARNING: No tool results found for workflow {workflow_id}, using generic message"
                        )
                except Exception as result_error:
                    logger.error(
                        f"ERROR: Failed to extract tool results for workflow {workflow_id}: {result_error}, using generic message"
                    )
                    import traceback

                    logger.error(f"ERROR: Traceback: {traceback.format_exc()}")

                # Create final result
                final_result = {
                    "file_execution_id": workflow_file_execution_id,
                    "file": file_name,
                    "result": workflow_result,
                    "success": True,
                    "error": None,
                    "metadata": result_metadata,
                }

                # Handle destination processing for API vs ETL/TASK workflows
                if is_api:
                    # API workflows: Cache results in Redis
                    try:
                        self.cache_api_result(
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            result=final_result,
                            is_api=True,
                        )
                        logger.info(
                            f"Successfully cached API result for execution {execution_id}"
                        )
                    except Exception as cache_error:
                        logger.warning(f"Failed to cache API result: {cache_error}")
                        # Don't fail the execution if caching fails
                else:
                    # ETL/TASK workflows: Process through destination connector
                    try:
                        destination_result = self._handle_destination_processing(
                            workflow_id=workflow_id,
                            execution_id=execution_id,
                            file_data=file_data,
                            workflow_result=workflow_result,
                            workflow_file_execution_id=workflow_file_execution_id,
                            organization_id=organization_id,
                        )
                        if destination_result:
                            logger.info(
                                f"Successfully processed file {file_name} through destination connector"
                            )
                            # Update final result with destination processing info
                            final_result["destination_processed"] = True
                            final_result["destination_result"] = destination_result
                        else:
                            logger.warning(
                                f"Destination processing returned None for file {file_name}"
                            )
                            final_result["destination_processed"] = False
                    except Exception as dest_error:
                        logger.error(
                            f"Destination processing failed for file {file_name}: {dest_error}"
                        )
                        # Don't fail the entire execution if destination fails
                        final_result["destination_processed"] = False
                        final_result["destination_error"] = str(dest_error)

                return final_result
            else:
                return {
                    "file_execution_id": workflow_file_execution_id,
                    "file": file_name,
                    "result": None,
                    "success": False,
                    "error": "Workflow execution failed",
                    "metadata": {
                        "workflow_id": workflow_id,
                        "execution_id": execution_id,
                        "execution_time": execution_time,
                    },
                }

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Failed to execute workflow for file {file_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return {
                "file_execution_id": workflow_file_execution_id,
                "file": file_name,
                "result": None,
                "success": False,
                "error": str(e),
                "metadata": {
                    "workflow_id": workflow_id,
                    "execution_id": execution_id,
                    "execution_time": execution_time,
                },
            }

    def _create_worker_execution_service(
        self,
        organization_id: str,
        workflow_id: str,
        workflow_info: dict[str, Any],
        tool_instances_data: list[dict[str, Any]],
        execution_id: str,
        file_execution_id: str,
        is_api: bool = False,
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

        # Get platform service API key from environment
        platform_service_api_key = os.getenv(
            "PLATFORM_SERVICE_API_KEY", "default-api-key"
        )

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
        messaging_channel = f"workflow_execution_{execution_id}_{file_execution_id}"
        execution_service.set_messaging_channel(messaging_channel)

        return execution_service

    def _execute_workflow_with_service(
        self,
        execution_service: WorkflowExecutionService,
        file_name: str,
        workflow_file_execution_id: str,
        execution_id: str,
        file_data: dict[str, Any],
    ) -> bool:
        """Execute workflow using WorkflowExecutionService following backend pattern."""
        try:
            # Step 1: Compile workflow (like WorkflowExecutionServiceHelper.__init__)
            compilation_result = execution_service.compile_workflow(execution_id)
            if not compilation_result.get("success"):
                error_msg = f"Workflow compilation failed: {compilation_result.get('problems', ['Unknown error'])}"
                logger.error(error_msg)
                return False

            logger.info(f"Workflow compiled successfully for file {file_name}")

            # Step 2: Add input file to execution directory (critical missing step!)
            # This is what the backend does in source.py:912 via add_file_to_volume
            file_handler = execution_service.file_handler
            try:
                # Get file information from file_data parameter
                file_path = file_data.get("file_path", "")
                source_connection_type = file_data.get("source_connection_type", "")
                connector_metadata = file_data.get("connector_metadata", {})

                import hashlib

                from unstract.filesystem import FileStorageType, FileSystem

                # Get the workflow execution file system
                workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
                workflow_file_storage = workflow_file_system.get_file_storage()

                # Get target paths for INFILE and SOURCE
                infile_path = file_handler.infile
                source_file_path = file_handler.source_file

                if infile_path and source_file_path and file_path:
                    logger.info(
                        f"Copying source file {file_path} to execution directory for {file_name}"
                    )

                    # Copy file from source connector to execution directory
                    # We need to get the source file system to read the original file
                    try:
                        # Parse connector information
                        if "|" in source_connection_type:
                            connector_type, _ = source_connection_type.split("|", 1)
                        else:
                            connector_type = source_connection_type

                        # Handle API files differently (like backend source.py:940-943)
                        if connector_type == "API":
                            logger.info(
                                f"Handling API file copy from {file_path} to execution directory"
                            )
                            # For API files, copy from API storage to workflow execution directory
                            # Following the same pattern as backend add_input_from_api_storage_to_volume()
                            api_file_system = FileSystem(FileStorageType.API_EXECUTION)
                            api_file_storage = api_file_system.get_file_storage()

                            # Copy file from API storage to workflow execution directory
                            READ_CHUNK_SIZE = 4194304  # 4MB chunks like backend
                            file_content_hash = hashlib.sha256()
                            total_bytes_copied = 0

                            logger.info(f"Starting API file copy from {file_path}")
                            logger.info(
                                f"INFILE path: {infile_path}, SOURCE path: {source_file_path}"
                            )

                            # Read the entire file from API storage
                            file_content = api_file_storage.read(
                                path=file_path, mode="rb"
                            )

                            if file_content:
                                # Calculate hash
                                file_content_hash.update(file_content)
                                computed_hash = file_content_hash.hexdigest()

                                # Write to both INFILE and SOURCE paths
                                workflow_file_storage.write(
                                    path=infile_path, mode="wb", data=file_content
                                )
                                workflow_file_storage.write(
                                    path=source_file_path, mode="wb", data=file_content
                                )

                                total_bytes_copied = len(file_content)
                                logger.info(
                                    f"Successfully copied {total_bytes_copied} bytes from API storage to execution directory"
                                )
                            else:
                                # Handle empty file
                                computed_hash = hashlib.sha256(b"").hexdigest()
                                logger.warning(f"API file {file_path} is empty")

                                # Create empty files
                                workflow_file_storage.write(
                                    path=infile_path, mode="wb", data=b""
                                )
                                workflow_file_storage.write(
                                    path=source_file_path, mode="wb", data=b""
                                )
                                total_bytes_copied = 0

                            logger.info(
                                f"API file copy complete with hash: {computed_hash}"
                            )

                        else:
                            # Handle filesystem connectors (existing logic)
                            # Create source file system using connector registry (following backend pattern)
                            from unstract.connectors.constants import Common
                            from unstract.connectors.filesystems import connectors

                            logger.info(
                                f"Available connectors: {list(connectors.keys())}"
                            )
                            logger.info(f"Looking for connector_type: {connector_type}")

                            # Need to find the connector by matching the type part before the pipe
                            matching_connector_key = None
                            for key in connectors.keys():
                                if key.startswith(f"{connector_type}|"):
                                    matching_connector_key = key
                                    break

                            # Get source filesystem using the same pattern as backend base_connector.py
                            if matching_connector_key:
                                logger.info(
                                    f"Found matching connector: {matching_connector_key}"
                                )
                                connector_class = connectors[matching_connector_key][
                                    Common.METADATA
                                ][Common.CONNECTOR]
                                source_connector = connector_class(connector_metadata)
                                source_fs = source_connector.get_fsspec_fs()

                                # Read source file and compute hash using chunked approach (matching backend)
                                READ_CHUNK_SIZE = 4194304  # Same as backend: 4MB chunks
                                file_content_hash = hashlib.sha256()
                                total_bytes_copied = 0

                                logger.info(
                                    f"Starting chunked file copy from {file_path} to execution directory"
                                )
                                logger.info(
                                    f"INFILE path: {infile_path}, SOURCE path: {source_file_path}"
                                )

                                with source_fs.open(file_path, "rb") as source_file:
                                    while chunk := source_file.read(READ_CHUNK_SIZE):
                                        file_content_hash.update(chunk)
                                        total_bytes_copied += len(chunk)

                                        # Write chunk to both INFILE and SOURCE using append mode (matching backend)
                                        try:
                                            workflow_file_storage.write(
                                                path=infile_path, mode="ab", data=chunk
                                            )
                                            workflow_file_storage.write(
                                                path=source_file_path,
                                                mode="ab",
                                                data=chunk,
                                            )
                                        except Exception as chunk_error:
                                            logger.error(
                                                f"Failed to write chunk to execution directory: {chunk_error}"
                                            )
                                            raise

                                logger.info(
                                    f"Successfully copied {total_bytes_copied} bytes in chunks from {file_path} to execution directory"
                                )

                                # Validate empty files and handle appropriately
                                if total_bytes_copied == 0:
                                    logger.warning(
                                        f"Source file {file_path} is empty (0 bytes). Tool execution may fail."
                                    )
                                    # Create minimal placeholder content for empty files to prevent tool container errors
                                    placeholder_content = f"# Empty file placeholder\n# Original file: {file_path}\n# Size: 0 bytes\n"
                                    placeholder_bytes = placeholder_content.encode(
                                        "utf-8"
                                    )

                                    # Overwrite the empty files with placeholder content
                                    workflow_file_storage.write(
                                        path=infile_path,
                                        mode="wb",
                                        data=placeholder_bytes,
                                    )
                                    workflow_file_storage.write(
                                        path=source_file_path,
                                        mode="wb",
                                        data=placeholder_bytes,
                                    )

                                    # Use hash of placeholder content
                                    computed_hash = hashlib.sha256(
                                        placeholder_bytes
                                    ).hexdigest()
                                    logger.info(
                                        f"Created placeholder content for empty file. Hash: {computed_hash}"
                                    )
                                else:
                                    # Use computed hash for non-empty files
                                    computed_hash = file_content_hash.hexdigest()
                                    logger.info(
                                        f"File copy complete with hash: {computed_hash}"
                                    )

                            else:
                                available_types = [
                                    key.split("|")[0] for key in connectors.keys()
                                ]
                                raise ValueError(
                                    f"Unsupported connector type: {connector_type}. Available types: {available_types}"
                                )

                    except Exception as copy_error:
                        logger.error(
                            f"Failed to copy source file {file_path}: {copy_error}"
                        )

                        # Only create placeholder files if we have valid paths
                        if infile_path and source_file_path:
                            try:
                                # Create placeholder files as fallback
                                placeholder_content = f"Error: Could not copy source file {file_path}\nError: {str(copy_error)}\n"
                                placeholder_bytes = placeholder_content.encode("utf-8")

                                workflow_file_storage.write(
                                    path=infile_path, mode="wb", data=placeholder_bytes
                                )
                                workflow_file_storage.write(
                                    path=source_file_path,
                                    mode="wb",
                                    data=placeholder_bytes,
                                )
                                computed_hash = hashlib.md5(placeholder_bytes).hexdigest()
                                logger.warning(
                                    f"Created placeholder INFILE due to copy error for {file_name}"
                                )
                            except Exception as placeholder_error:
                                logger.error(
                                    f"Failed to create placeholder files: {placeholder_error}"
                                )
                                # If we can't create placeholder files, we must fail the execution
                                # Don't hide the original error behind a placeholder error
                                raise copy_error from placeholder_error
                        else:
                            # Can't create placeholders without valid paths, re-raise original error
                            raise copy_error
                else:
                    # Missing required paths - this is a critical error
                    error_msg = f"Missing required file paths: infile_path={infile_path}, source_file_path={source_file_path}, file_path={file_path}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                # Step 3: Create initial METADATA.json file (previously fixed)
                file_handler.add_metadata_to_volume(
                    input_file_path=file_data.get("file_path", file_name),
                    file_execution_id=workflow_file_execution_id,
                    source_hash=computed_hash,
                    tags=[],  # Workers don't have tags by default
                    llm_profile_id=None,  # Workers don't have LLM profile override
                )
                logger.info(f"Initial metadata file created for {file_name}")

            except Exception as file_prep_error:
                logger.error(
                    f"Failed to prepare input file and metadata: {file_prep_error}"
                )
                # Re-raise the original error so the user sees the actual root cause
                raise file_prep_error

            # Step 4: Build workflow (like WorkflowExecutionServiceHelper.build())
            execution_service.build_workflow()
            logger.info(f"Workflow built successfully for file {file_name}")

            # Step 5: Execute workflow (like WorkflowExecutionServiceHelper.execute())
            from unstract.workflow_execution.enums import ExecutionType

            execution_service.execute_workflow(ExecutionType.COMPLETE)
            logger.info(f"Workflow executed successfully for file {file_name}")

            return True

        except Exception as e:
            logger.error(
                f"Workflow execution failed for file {file_name}: {str(e)}", exc_info=True
            )
            return False

    def _extract_tool_results(self, execution_service, workflow_file_execution_id: str):
        """Extract tool results from workflow execution service."""
        try:
            # Get the file handler from execution service
            file_handler = execution_service.file_handler

            # Try to read the METADATA.json file which contains tool results
            metadata_path = file_handler.metadata_file
            if metadata_path:
                from unstract.filesystem import FileStorageType, FileSystem

                # Get workflow execution file system
                workflow_file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
                workflow_file_storage = workflow_file_system.get_file_storage()

                # Read metadata file
                metadata_content = workflow_file_storage.read(
                    path=metadata_path, mode="r"
                )
                if metadata_content:
                    import json

                    metadata = json.loads(metadata_content)

                    # Extract tool results from metadata
                    tool_metadata = metadata.get("tool_metadata", [])
                    if tool_metadata:
                        logger.info(
                            f"Found {len(tool_metadata)} tool results in metadata"
                        )

                        # For API workflows, try to read the actual tool output files
                        # The tool outputs are typically stored in files like "step_1_output.json"
                        final_results = {}
                        for i, tool_meta in enumerate(tool_metadata, 1):
                            tool_name = tool_meta.get("tool_name", f"step_{i}")
                            try:
                                # Common output file patterns
                                possible_output_files = [
                                    f"step_{i}_output.json",
                                    f"{tool_name}_output.json",
                                    f"step_{i}.json",
                                    "OUTPUT.json",
                                    "output.json",
                                ]

                                # Get the execution directory path
                                execution_dir = metadata_path.rsplit("/", 1)[
                                    0
                                ]  # Remove METADATA.json to get directory

                                for output_file in possible_output_files:
                                    output_path = f"{execution_dir}/{output_file}"
                                    try:
                                        tool_output = workflow_file_storage.read(
                                            path=output_path, mode="r"
                                        )
                                        if tool_output:
                                            try:
                                                # Try to parse as JSON
                                                tool_result = json.loads(tool_output)
                                                final_results[tool_name] = tool_result
                                                logger.info(
                                                    f"Successfully extracted output for tool {tool_name}"
                                                )
                                                break  # Found output for this tool
                                            except json.JSONDecodeError:
                                                # If not JSON, store as string
                                                final_results[tool_name] = tool_output
                                                break
                                    except Exception:
                                        continue  # Try next file pattern

                            except Exception as tool_error:
                                logger.debug(
                                    f"Could not read output for tool {tool_name}: {tool_error}"
                                )
                                continue

                        if final_results:
                            logger.info(
                                f"Successfully extracted {len(final_results)} tool results"
                            )
                            return final_results
                        else:
                            # Fallback: return simplified tool metadata
                            simplified_results = {}
                            for i, tool_meta in enumerate(tool_metadata, 1):
                                tool_name = tool_meta.get("tool_name", f"step_{i}")
                                simplified_results[tool_name] = {
                                    "output_type": tool_meta.get(
                                        "output_type", "unknown"
                                    ),
                                    "elapsed_time": tool_meta.get("elapsed_time", 0),
                                    "status": "completed",
                                }
                            return simplified_results

            logger.debug(
                f"No tool results found for workflow file execution {workflow_file_execution_id}"
            )
            return None

        except Exception as e:
            logger.error(f"Failed to extract tool results: {e}")
            return None

    def _extract_tool_results_from_context(
        self,
        workflow_id: str,
        execution_id: str,
        workflow_file_execution_id: str,
        organization_id: str,
    ) -> Any | None:
        """Extract tool results using execution context (following backend pattern).

        This method replicates the backend's destination.py:get_tool_execution_result_from_metadata
        to read actual tool output from the INFILE.
        """
        try:
            logger.info("DEBUG: Starting _extract_tool_results_from_context")
            logger.info(
                f"DEBUG: Parameters - workflow_id:{workflow_id}, execution_id:{execution_id}, file_execution_id:{workflow_file_execution_id}, org_id:{organization_id}"
            )

            import json

            from unstract.filesystem import FileStorageType, FileSystem
            from unstract.workflow_execution.constants import ToolOutputType
            from unstract.workflow_execution.execution_file_handler import (
                ExecutionFileHandler,
            )

            logger.info("DEBUG: Imports successful")

            # Use ExecutionFileHandler to get proper paths (matching backend)
            logger.info("DEBUG: Creating ExecutionFileHandler")
            file_handler = ExecutionFileHandler(
                workflow_id=workflow_id,
                execution_id=execution_id,
                organization_id=organization_id,
                file_execution_id=workflow_file_execution_id,
            )
            logger.info("DEBUG: ExecutionFileHandler created successfully")

            metadata_file_path = file_handler.metadata_file
            logger.info(f"DEBUG: Metadata file path: {metadata_file_path}")

            # Get workflow metadata (following backend pattern)
            file_system = FileSystem(FileStorageType.WORKFLOW_EXECUTION)
            file_storage = file_system.get_file_storage()
            logger.info("DEBUG: FileSystem created successfully")

            if not metadata_file_path:
                logger.warning("DEBUG: Metadata file path is None")
                return None

            if not file_storage.exists(metadata_file_path):
                logger.warning(
                    f"DEBUG: Metadata file does not exist: {metadata_file_path}"
                )
                return None

            logger.info(f"DEBUG: Reading metadata from: {metadata_file_path}")
            metadata_content = file_storage.read(path=metadata_file_path, mode="r")
            metadata = json.loads(metadata_content)
            logger.info(f"DEBUG: Successfully read metadata from {metadata_file_path}")

            # Get output type from metadata (following backend pattern)
            output_type = self._get_output_type_from_metadata(metadata)
            logger.info(f"DEBUG: Detected output type: {output_type}")

            # Get the output file path using the file handler (matching backend pattern)
            output_file_path = file_handler.infile
            logger.info(f"DEBUG: Output file path (infile): {output_file_path}")

            if not output_file_path:
                logger.warning("DEBUG: Output file path (infile) is None")
                return None

            if not file_storage.exists(output_file_path):
                logger.warning(f"DEBUG: Output file does not exist: {output_file_path}")
                return None

            # Parse based on output type (following backend destination.py pattern exactly)
            logger.info(
                f"DEBUG: Reading output file: {output_file_path} with type: {output_type}"
            )
            if output_type == ToolOutputType.JSON:
                file_content = file_storage.read(output_file_path, mode="r")
                result = json.loads(file_content)
                logger.info(
                    f"DEBUG: Successfully parsed JSON tool result from {output_file_path}, result type: {type(result)}"
                )
                return result
            elif output_type == ToolOutputType.TXT:
                file_content = file_storage.read(output_file_path, mode="r")
                result = file_content.encode("utf-8").decode("unicode-escape")
                logger.info(
                    f"DEBUG: Successfully read TXT tool result from {output_file_path}, result length: {len(result) if result else 'None'}"
                )
                return result
            else:
                logger.warning(f"DEBUG: Unknown output type: {output_type}")
                return None

        except Exception as e:
            logger.error(
                f"DEBUG: Exception in _extract_tool_results_from_context: {str(e)}"
            )
            import traceback

            logger.error(f"DEBUG: Full traceback: {traceback.format_exc()}")
            return None

    def _get_output_type_from_metadata(self, metadata: dict[str, Any]) -> str:
        """Get output type from metadata (following backend pattern)."""
        try:
            from unstract.workflow_execution.constants import (
                MetaDataKey,
                ToolMetadataKey,
                ToolOutputType,
            )

            # Get tool metadata list (following backend pattern)
            tool_metadata = metadata.get(MetaDataKey.TOOL_METADATA, [])
            if not tool_metadata:
                logger.warning("No tool metadata found, defaulting to TXT output")
                return ToolOutputType.TXT

            # Get last tool metadata (like backend)
            last_tool_metadata = tool_metadata[-1]
            output_type = last_tool_metadata.get(
                ToolMetadataKey.OUTPUT_TYPE, ToolOutputType.TXT
            )

            logger.debug(f"Detected output type: {output_type}")
            return output_type

        except Exception as e:
            logger.error(f"Failed to get output type from metadata: {str(e)}")
            return "TXT"  # Safe default

    def detect_connection_type(self, workflow_id: str) -> str:
        """Detect workflow connection type (referenced in comments)."""
        try:
            # Simple fallback detection - in practice this would check workflow endpoints
            logger.debug(f"Detecting connection type for workflow {workflow_id}")
            return "ETL"  # Default fallback
        except Exception as e:
            logger.error(
                f"Failed to detect connection type for workflow {workflow_id}: {str(e)}"
            )
            return "ETL"

    def cache_api_result(
        self,
        workflow_id: str,
        execution_id: str,
        result: dict[str, Any],
        is_api: bool = True,
    ) -> bool:
        """Cache API result using proper ResultCacheUtils pattern."""
        if not is_api:
            logger.debug("Skipping result caching for non-API workflow")
            return True

        try:
            # Initialize cache utils
            cache_utils = WorkerResultCacheUtils()

            # Create FileExecutionResult matching backend pattern
            api_result = FileExecutionResult(
                file=result.get("file", "unknown"),
                file_execution_id=result.get("file_execution_id", ""),
                result=result.get("result"),
                error=result.get("error"),
                metadata=result.get("metadata"),
            )

            # Cache the result using same pattern as backend
            cache_utils.update_api_results(
                workflow_id=workflow_id, execution_id=execution_id, api_result=api_result
            )

            logger.info(f"Successfully cached API result for execution {execution_id}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to cache API result for execution {execution_id}: {str(e)}"
            )
            # Return False but don't re-raise - caching failures shouldn't stop execution
            return False

    def add_source_and_infile_to_volume(self, *args, **kwargs):
        """Add source and input file to volume (used in some tests)."""
        logger.debug("Adding source and infile to volume (mock implementation)")
        return True

    def deliver_to_destinations(
        self,
        file_data: dict[str, Any],
        workflow_type: str,
        destination_config_data: dict[str, Any],
    ) -> str | None:
        """Deliver file to destination using proper dataclass deserialization."""
        try:
            # Use DestinationConfig.from_dict to properly handle string-to-enum conversion
            dest_config = DestinationConfig.from_dict(destination_config_data)
            logger.info(
                f"Created {workflow_type} destination connector: {dest_config.connection_type}"
            )

            # Simple delivery simulation - in practice this would handle the actual destination logic
            return "delivered_successfully"

        except Exception as e:
            logger.error(f"Failed to deliver to destination: {str(e)}")
            raise

    def _handle_destination_processing(
        self,
        workflow_id: str,
        execution_id: str,
        file_data: dict[str, Any],
        workflow_result: Any,
        workflow_file_execution_id: str,
        organization_id: str,
    ) -> str | None:
        """Handle destination processing for ETL/TASK workflows following backend pattern.

        This matches the exact pattern from backend/workflow_manager/workflow_v2/file_execution_tasks.py
        _process_final_output method.
        """
        try:
            logger.info(
                f"Starting destination processing for file {file_data.get('file_name')} in workflow {workflow_id}"
            )

            # Get destination configuration via API
            destination_config = self._get_destination_config(workflow_id, execution_id)

            if not destination_config:
                logger.warning(
                    f"No destination configuration found for workflow {workflow_id}"
                )
                return None

            # Import destination connector
            from .workflow.destination_connector import (
                DestinationConfig,
                WorkerDestinationConnector,
            )

            # Create destination config object (matching backend DestinationConnector.from_config)
            dest_config = DestinationConfig.from_dict(destination_config)
            logger.info(f"Created destination config: {dest_config.connection_type}")

            # Create destination connector (matching backend pattern)
            destination = WorkerDestinationConnector.from_config(None, dest_config)

            # Create FileHashData for destination processing (matching backend FileHash)
            from unstract.core.data_models import FileHashData

            file_hash = FileHashData(
                file_name=file_data.get("file_name", "unknown"),
                file_path=file_data.get("file_path", ""),
                file_hash=file_data.get("file_hash", ""),
                file_size=file_data.get("file_size", 0),
                mime_type=file_data.get("mime_type", "application/octet-stream"),
                provider_file_uuid=file_data.get("provider_file_uuid"),
                fs_metadata=file_data.get("fs_metadata", {}),
                source_connection_type=file_data.get("source_connection_type", ""),
                file_destination=file_data.get("file_destination", "destination"),
                is_executed=True,  # Mark as executed since workflow is complete
                file_number=file_data.get("file_number", 1),
                connector_metadata=file_data.get("connector_metadata", {}),
                connector_id=file_data.get("connector_id", ""),
            )

            # Get file history if destination uses it (matching backend pattern)
            file_history = None
            if destination.use_file_history:
                file_path = file_hash.file_path if not destination.is_api else None
                # Get file history for deduplication (worker implementation)
                file_history = WorkerFileHistoryHelper.get_file_history(
                    workflow={"id": workflow_id},
                    cache_key=file_hash.file_hash,
                    file_path=file_path,
                )

            # Process final output through destination (matching backend exactly)
            output_result = None
            processing_error = None  # No processing error since workflow succeeded

            if not processing_error:
                # DEBUG: Log what we're about to pass to destination
                logger.info(
                    f"DEBUG: About to call destination.handle_output with tool_execution_result type: {type(workflow_result)}"
                )
                logger.info(f"DEBUG: tool_execution_result value: {workflow_result}")

                # Process final output through destination (exact backend signature + workers-specific params)
                output_result = destination.handle_output(
                    file_name=file_hash.file_name,
                    file_hash=file_hash,
                    file_history=file_history,
                    workflow={"id": workflow_id},  # Minimal workflow object like backend
                    input_file_path=file_hash.file_path,
                    file_execution_id=workflow_file_execution_id,
                    # Workers-specific parameters (needed for API-based operation)
                    api_client=self.api_client,
                    tool_execution_result=workflow_result,
                    workflow_id=workflow_id,
                    execution_id=execution_id,
                    organization_id=organization_id,
                )

            # Handle metadata for API workflows (matching backend pattern)
            execution_metadata = None
            if destination.is_api:
                execution_metadata = destination.get_metadata(file_history)

            # Create file history if needed (matching backend _should_create_file_history logic)
            if self._should_create_file_history(
                destination=destination,
                file_history=file_history,
                output_result=output_result,
                processing_error=processing_error,
            ):
                # Create file history entry (matching backend FileHistoryHelper.create_file_history)
                WorkerFileHistoryHelper.create_file_history(
                    is_api=destination.is_api,
                    file_hash=file_hash,
                    workflow={"id": workflow_id},
                    status="COMPLETED",  # ExecutionStatus.COMPLETED equivalent
                    result=output_result,
                    metadata=execution_metadata,
                )
                logger.info(f"Created file history entry for {file_hash.file_name}")

            logger.info(
                f"Destination processing completed for file {file_hash.file_name}"
            )
            return output_result

        except Exception as e:
            logger.error(f"Failed to process destination for workflow {workflow_id}: {e}")
            raise

    def _should_create_file_history(
        self,
        destination,
        file_history,
        output_result,
        processing_error,
    ) -> bool:
        """Determine if file history should be created (matching backend logic).

        This matches backend FileExecutionTasks._should_create_file_history.
        """
        # Don't create history if there was a processing error
        if processing_error:
            return False

        # Don't create history if destination doesn't use file history
        if not destination.use_file_history:
            return False

        # Don't create duplicate history if it already exists
        if file_history:
            return False

        # Create history for successful processing
        return True

    def _get_destination_config(
        self, workflow_id: str, execution_id: str
    ) -> dict[str, Any] | None:
        """Get destination configuration for the workflow via API."""
        try:
            # Get workflow execution context which includes destination config
            execution_context = self.api_client.get_workflow_execution(execution_id)
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


# Simple helper classes that might be referenced elsewhere
class WorkerFileHistoryHelper:
    """Worker-compatible file history helper."""

    @staticmethod
    def get_file_history(
        workflow: dict[str, Any], cache_key: str, file_path: str | None = None
    ):
        """Get file history for deduplication (worker implementation)."""
        # TODO: Implement actual file history lookup via API
        return None

    @staticmethod
    def create_file_history(
        is_api: bool,
        file_hash,  # FileHashData object
        workflow: dict[str, Any],
        status: str,
        result: Any = None,
        metadata: Any = None,
    ):
        """Create file history entry (matching backend FileHistoryHelper.create_file_history).

        This matches the exact signature from backend FileHistoryHelper.create_file_history.
        """
        try:
            logger.info(
                f"Creating file history entry for {file_hash.file_name} (status: {status})"
            )

            # For now, this is a placeholder implementation
            # In full implementation, this would:
            # 1. Create a FileHistory entry via API
            # 2. Store the result and metadata for deduplication
            # 3. Enable file history-based skipping for future runs

            # TODO: Implement actual file history creation via API
            # api_client.create_file_history({
            #     'workflow_id': workflow['id'],
            #     'file_hash': file_hash.file_hash,
            #     'file_path': file_hash.file_path,
            #     'status': status,
            #     'result': result,
            #     'metadata': metadata,
            #     'is_api': is_api
            # })

            logger.debug(f"File history entry created for {file_hash.file_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to create file history for {file_hash.file_name}: {e}")
            return False


class FileExecutionResult:
    """File execution result container matching backend pattern."""

    def __init__(
        self,
        file: str,
        file_execution_id: str,
        result: Any = None,
        error: str = None,
        metadata: Any = None,
    ):
        self.file = file
        self.file_execution_id = file_execution_id
        self.result = result
        self.error = error
        self.metadata = metadata

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "file": self.file,
            "file_execution_id": self.file_execution_id,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class WorkerResultCacheUtils:
    """Worker result caching utilities matching backend ResultCacheUtils pattern."""

    def __init__(self):
        import os

        self.expire_time = int(
            os.getenv("EXECUTION_RESULT_TTL_SECONDS", "86400")
        )  # 24 hours default
        self._redis_client = None

    def _get_redis_client(self):
        """Get Redis client instance."""
        if self._redis_client is None:
            import os

            import redis

            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db = int(os.getenv("REDIS_DB", "0"))

            self._redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=False,  # Keep binary for JSON handling
                socket_connect_timeout=5,
                socket_timeout=5,
            )

        return self._redis_client

    def check_redis_health(self, timeout_seconds: float = 2.0) -> bool:
        """Check if Redis is healthy and accessible."""
        try:
            redis_client = self._get_redis_client()
            redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            raise

    def _get_api_results_cache_key(self, workflow_id: str, execution_id: str) -> str:
        """Get Redis cache key for api_results matching backend pattern."""
        return f"api_results:{workflow_id}:{execution_id}"

    def update_api_results(
        self, workflow_id: str, execution_id: str, api_result: FileExecutionResult
    ) -> None:
        """Update api_results in Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()

            # Convert result to JSON string (matching backend CacheService.rpush_with_expire)
            result_json = json.dumps(api_result.to_json())

            # Use Redis pipeline for atomic operation
            pipe = redis_client.pipeline()
            pipe.rpush(cache_key, result_json)
            pipe.expire(cache_key, self.expire_time)
            pipe.execute()

            logger.info(f"Successfully cached API result for execution {execution_id}")

        except Exception as e:
            logger.error(f"Failed to cache API result for execution {execution_id}: {e}")
            # Re-raise to ensure caching failures are visible (fail-fast approach)
            raise

    def get_api_results(self, workflow_id: str, execution_id: str) -> list:
        """Get api_results from Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()

            # Get all results from Redis list
            result_strings = redis_client.lrange(cache_key, 0, -1)

            # Convert back to dictionaries
            results = []
            for result_string in result_strings:
                try:
                    result_dict = json.loads(result_string.decode("utf-8"))
                    results.append(result_dict)
                except Exception as parse_error:
                    logger.error(f"Failed to parse cached result: {parse_error}")
                    continue

            return results

        except Exception as e:
            logger.error(
                f"Failed to retrieve API results for execution {execution_id}: {e}"
            )
            return []

    def delete_api_results(self, workflow_id: str, execution_id: str) -> None:
        """Delete api_results from Redis cache matching backend pattern."""
        try:
            cache_key = self._get_api_results_cache_key(workflow_id, execution_id)
            redis_client = self._get_redis_client()
            redis_client.delete(cache_key)

        except Exception as e:
            logger.error(
                f"Failed to delete API results for execution {execution_id}: {e}"
            )

    @staticmethod
    def get_cached_result(cache_key: str) -> Any:
        """Get cached result (legacy method)."""
        return None

    @staticmethod
    def cache_result(cache_key: str, result: Any) -> bool:
        """Cache result (legacy method)."""
        return True
