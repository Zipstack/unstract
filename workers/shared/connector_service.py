"""Worker-Native Connector Service

This module provides worker-native connector operations for destination processing
without backend dependency. Handles all destination delivery within workers.
"""

import time
from typing import Any

# Import shared operations and data models
from unstract.connectors.operations import ConnectorOperations
from unstract.core.data_models import FileHashData

from .api_client import InternalAPIClient
from .logging_utils import WorkerLogger
from .retry_utils import circuit_breaker, retry

logger = WorkerLogger.get_logger(__name__)


class WorkerConnectorService:
    """Handle connector operations within workers with database persistence"""

    def __init__(self, api_client: InternalAPIClient):
        """Initialize connector service with API client for database operations only.

        Args:
            api_client: API client for database operations
        """
        self.api_client = api_client  # Database operations only

    @retry(max_attempts=3, base_delay=2.0)
    @circuit_breaker(failure_threshold=5, recovery_timeout=120.0)
    def process_destination_delivery(
        self,
        files: list[FileHashData],
        destination_config: dict[str, Any],
        workflow_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Process destination delivery using worker-native connector operations.

        This replaces backend destination processing with worker-native operations
        while maintaining database persistence through API client.

        Args:
            files: List of FileHashData objects to deliver
            destination_config: Destination connector configuration
            workflow_context: Workflow execution context

        Returns:
            Dictionary with delivery results
        """
        logger.info(f"Processing destination delivery for {len(files)} files")

        # Validate destination configuration using shared logic
        validation = ConnectorOperations.validate_destination_config(destination_config)
        if not validation["is_valid"]:
            raise ValueError(f"Invalid destination config: {validation['errors']}")

        # Prepare destination configuration
        prepared_config = ConnectorOperations.prepare_destination_config(
            connector_data=destination_config, workflow_context=workflow_context
        )

        # Use connector_id if available, fall back to connection_type for legacy support
        connector_id = prepared_config.get("connector_id") or prepared_config.get(
            "connection_type"
        )
        connector_settings = prepared_config["settings"]

        if not connector_id:
            raise ValueError(
                "Missing connector_id or connection_type in destination configuration"
            )

        delivery_start_time = time.time()
        delivered_files = 0
        failed_files = 0
        delivery_results = []

        try:
            # Get appropriate connector using registry pattern
            connector = self._get_destination_connector(connector_id, connector_settings)

            logger.info(f"Created {connector_id} destination connector")

            # Process each file through destination connector
            for file_data in files:
                file_start_time = time.time()

                try:
                    # Deliver file using connector
                    delivery_result = self._deliver_single_file(
                        connector=connector,
                        file_data=file_data,
                        destination_config=prepared_config,
                        workflow_context=workflow_context,
                    )

                    file_delivery_time = time.time() - file_start_time

                    if delivery_result.get("success"):
                        delivered_files += 1

                        # Create file history record via database API
                        self._create_file_history_record(
                            file_data=file_data,
                            delivery_result=delivery_result,
                            workflow_context=workflow_context,
                            delivery_time=file_delivery_time,
                        )

                        delivery_results.append(
                            {
                                "file_name": file_data.file_name,
                                "status": "delivered",
                                "destination_path": delivery_result.get(
                                    "destination_path"
                                ),
                                "delivery_time": file_delivery_time,
                                "metadata": delivery_result.get("metadata", {}),
                            }
                        )

                        logger.debug(
                            f"Successfully delivered {file_data.file_name} in {file_delivery_time:.2f}s"
                        )

                    else:
                        failed_files += 1
                        error_msg = delivery_result.get("error", "Unknown delivery error")

                        delivery_results.append(
                            {
                                "file_name": file_data.file_name,
                                "status": "failed",
                                "error": error_msg,
                                "delivery_time": file_delivery_time,
                            }
                        )

                        logger.warning(
                            f"Failed to deliver {file_data.file_name}: {error_msg}"
                        )

                except Exception as e:
                    failed_files += 1
                    file_delivery_time = time.time() - file_start_time
                    error_msg = str(e)

                    delivery_results.append(
                        {
                            "file_name": file_data.file_name,
                            "status": "failed",
                            "error": error_msg,
                            "delivery_time": file_delivery_time,
                        }
                    )

                    logger.error(
                        f"Exception delivering {file_data.file_name}: {error_msg}"
                    )

            total_delivery_time = time.time() - delivery_start_time

            # Determine overall delivery status
            if delivered_files > 0 and failed_files == 0:
                status = "success"
            elif delivered_files > 0 and failed_files > 0:
                status = "partial"
            elif failed_files > 0:
                status = "failed"
            else:
                status = "unknown"

            final_result = {
                "status": status,
                "connector_id": connector_id,
                "delivered_files": delivered_files,
                "failed_files": failed_files,
                "total_files": len(files),
                "total_delivery_time": total_delivery_time,
                "delivery_results": delivery_results,
            }

            logger.info(
                f"Destination delivery complete: {delivered_files}/{len(files)} files delivered "
                f"to {connector_id} in {total_delivery_time:.2f}s"
            )

            return final_result

        except Exception as e:
            error_msg = f"Destination delivery failed: {str(e)}"
            logger.error(error_msg, exc_info=True)

            return {
                "status": "failed",
                "connector_id": connector_id,
                "delivered_files": 0,
                "failed_files": len(files),
                "total_files": len(files),
                "error": error_msg,
                "delivery_results": [],
            }

    def _get_destination_connector(
        self, connector_id: str, connector_settings: dict[str, Any]
    ):
        """Get destination connector using exact backend registry pattern.

        This method uses the same connector registry pattern as:
        - backend/workflow_manager/endpoint_v2/destination.py
        - backend/workflow_manager/endpoint_v2/base_connector.py

        Args:
            connector_id: Connector ID from registry (not connection_type)
            connector_settings: Connector configuration settings

        Returns:
            Connector instance

        Raises:
            ValueError: If connector_id is not supported
            ImportError: If connector registry not available
        """
        try:
            # Try filesystem connector first
            try:
                return ConnectorOperations.get_fs_connector(
                    connector_id=connector_id, settings=connector_settings
                )
            except ValueError:
                # Not a filesystem connector, try database connector
                try:
                    return ConnectorOperations.get_db_connector(
                        connector_id=connector_id, settings=connector_settings
                    )
                except ValueError:
                    # Final fallback - legacy connection_type handling for backward compatibility
                    return self._get_legacy_connector(connector_id, connector_settings)

        except ImportError as e:
            raise ImportError(
                f"Connector registry not available for {connector_id}: {str(e)}"
            )

    def _get_legacy_connector(
        self, connection_type: str, connector_settings: dict[str, Any]
    ):
        """Legacy connector factory for backward compatibility.

        This method is kept for backward compatibility with existing workflows
        that still use connection_type instead of connector_id.

        Args:
            connection_type: Legacy connection type
            connector_settings: Connector configuration settings

        Returns:
            Connector instance

        Raises:
            ValueError: If connection type is not supported
        """
        connection_type_upper = connection_type.upper()

        # Map legacy connection types to probable connector IDs and try registry first
        legacy_mapping = {
            "FILESYSTEM": "LOCAL_STORAGE",
            "LOCAL_FS": "LOCAL_STORAGE",
            "LOCAL": "LOCAL_STORAGE",
            "S3": "S3",
            "AWS_S3": "S3",
            "GCS": "GCS",
            "GOOGLE_CLOUD_STORAGE": "GCS",
            "POSTGRESQL": "POSTGRESQL",
            "POSTGRES": "POSTGRESQL",
            "MYSQL": "MYSQL",
            "BIGQUERY": "BIGQUERY",
            "SNOWFLAKE": "SNOWFLAKE",
        }

        # Try to map to actual connector ID
        if connection_type_upper in legacy_mapping:
            try:
                mapped_connector_id = legacy_mapping[connection_type_upper]
                return self._get_destination_connector(
                    mapped_connector_id, connector_settings
                )
            except (ValueError, ImportError):
                pass

        # Final fallback - raise error with helpful message
        raise ValueError(
            f"Unsupported destination connector: {connection_type}. "
            f"Please use connector_id from the connector registry instead of connection_type."
        )

    def _deliver_single_file(
        self,
        connector,
        file_data: FileHashData,
        destination_config: dict[str, Any],
        workflow_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Deliver single file using connector.

        Args:
            connector: Destination connector instance
            file_data: FileHashData object
            destination_config: Destination configuration
            workflow_context: Workflow context

        Returns:
            Dictionary with delivery result
        """
        try:
            # Prepare delivery parameters
            delivery_params = {
                "file_path": file_data.file_path,
                "file_name": file_data.file_name,
                "file_size": file_data.file_size,
                "file_hash": file_data.file_hash,
                "mime_type": file_data.mime_type,
                "workflow_id": workflow_context.get("workflow_id"),
                "execution_id": workflow_context.get("execution_id"),
                "organization_id": workflow_context.get("organization_id"),
            }

            # Call connector's delivery method
            if hasattr(connector, "deliver_file"):
                result = connector.deliver_file(**delivery_params)
            elif hasattr(connector, "upload_file"):
                result = connector.upload_file(**delivery_params)
            elif hasattr(connector, "insert_data"):
                # For database connectors
                result = connector.insert_data(**delivery_params)
            else:
                raise AttributeError(
                    "Connector does not have a supported delivery method"
                )

            # Normalize result format
            if isinstance(result, bool):
                return {
                    "success": result,
                    "destination_path": destination_config.get("settings", {}).get(
                        "path", ""
                    ),
                    "metadata": {},
                }
            elif isinstance(result, dict):
                return {
                    "success": result.get("success", True),
                    "destination_path": result.get(
                        "path", result.get("destination_path", "")
                    ),
                    "metadata": result.get("metadata", {}),
                    "error": result.get("error"),
                }
            else:
                return {
                    "success": True,
                    "destination_path": str(result) if result else "",
                    "metadata": {},
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "destination_path": "",
                "metadata": {},
            }

    def _create_file_history_record(
        self,
        file_data: FileHashData,
        delivery_result: dict[str, Any],
        workflow_context: dict[str, Any],
        delivery_time: float,
    ) -> bool:
        """Create file history record via database API.

        Args:
            file_data: FileHashData object
            delivery_result: Delivery result information
            workflow_context: Workflow context
            delivery_time: Time taken for delivery

        Returns:
            True if record created successfully
        """
        try:
            file_history_data = {
                "file_name": file_data.file_name,
                "file_path": file_data.file_path,
                "file_hash": file_data.file_hash,
                "provider_file_uuid": file_data.provider_file_uuid,
                "status": "DELIVERED",
                "destination_path": delivery_result.get("destination_path", ""),
                "delivery_metadata": {
                    "delivery_time": delivery_time,
                    "destination_metadata": delivery_result.get("metadata", {}),
                    "delivery_timestamp": time.time(),
                },
                "mime_type": file_data.mime_type,
                "file_size": file_data.file_size,
            }

            # Create file history via database API
            self.api_client.create_file_history(
                workflow_id=workflow_context["workflow_id"], file_data=file_history_data
            )

            logger.debug(f"Created file history record for {file_data.file_name}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to create file history for {file_data.file_name}: {str(e)}"
            )
            return False

    def test_destination_connectivity(
        self, destination_config: dict[str, Any], organization_id: str
    ) -> dict[str, Any]:
        """Test destination connector connectivity using registry pattern.

        Args:
            destination_config: Destination configuration
            organization_id: Organization ID for context

        Returns:
            Dictionary with connectivity test results
        """
        logger.info(f"Testing destination connectivity for org {organization_id}")

        try:
            # Validate configuration first
            validation = ConnectorOperations.validate_destination_config(
                destination_config
            )
            if not validation["is_valid"]:
                return {
                    "is_reachable": False,
                    "connector_id": destination_config.get("connector_id")
                    or destination_config.get("connection_type"),
                    "errors": validation["errors"],
                    "response_time_ms": None,
                }

            # Use connector_id if available, fall back to connection_type for legacy support
            connector_id = destination_config.get(
                "connector_id"
            ) or destination_config.get("connection_type")
            connector_settings = destination_config["settings"]

            if not connector_id:
                return {
                    "is_reachable": False,
                    "connector_id": None,
                    "errors": [
                        "Missing connector_id or connection_type in configuration"
                    ],
                    "response_time_ms": None,
                }

            test_start_time = time.time()

            # Get connector using registry pattern and test connection
            self._get_destination_connector(connector_id, connector_settings)

            # Test connectivity using shared logic
            health_result = ConnectorOperations.get_connector_health(
                connector_id=connector_id, settings=connector_settings
            )

            response_time = int((time.time() - test_start_time) * 1000)

            result = {
                "is_reachable": health_result["is_healthy"],
                "connector_id": connector_id,
                "response_time_ms": response_time,
                "errors": health_result.get("errors", []),
            }

            logger.info(
                f"Destination connectivity test: {'PASSED' if health_result['is_healthy'] else 'FAILED'} "
                f"({response_time}ms)"
            )

            return result

        except Exception as e:
            error_msg = f"Destination connectivity test failed: {str(e)}"
            logger.error(error_msg)

            return {
                "is_reachable": False,
                "connector_id": destination_config.get("connector_id")
                or destination_config.get("connection_type"),
                "errors": [error_msg],
                "response_time_ms": None,
            }

    def get_destination_capabilities(
        self, destination_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Get destination connector capabilities using registry pattern.

        Args:
            destination_config: Destination configuration

        Returns:
            Dictionary with connector capabilities
        """
        # Use connector_id if available, fall back to connection_type for legacy support
        connector_id = destination_config.get("connector_id") or destination_config.get(
            "connection_type", ""
        )

        capabilities = {
            "connector_id": connector_id,
            "supports_batch": True,
            "supports_streaming": False,
            "supports_transactions": False,
            "supported_formats": ["json"],
            "max_file_size": None,
            "concurrent_uploads": 1,
        }

        # Determine capabilities based on connector_id pattern
        connector_id_upper = connector_id.upper()

        # Database-specific capabilities (check against actual DB connector IDs)
        if any(
            db_id in connector_id_upper
            for db_id in ["POSTGRESQL", "MYSQL", "BIGQUERY", "SNOWFLAKE"]
        ):
            capabilities.update(
                {
                    "supports_transactions": True,
                    "supports_streaming": True,
                    "supported_formats": ["json", "csv", "parquet"],
                    "concurrent_uploads": 5,
                }
            )

        # File system capabilities (check against actual FS connector IDs)
        elif any(
            fs_id in connector_id_upper
            for fs_id in ["S3", "GCS", "LOCAL_STORAGE", "SFTP", "BOX"]
        ):
            capabilities.update(
                {
                    "supports_streaming": True,
                    "supported_formats": ["json", "csv", "txt", "pdf", "xlsx"],
                    "max_file_size": 5 * 1024 * 1024 * 1024,  # 5GB
                    "concurrent_uploads": 10,
                }
            )

        # API capabilities
        elif "API" in connector_id_upper:
            capabilities.update(
                {
                    "supports_batch": False,
                    "supported_formats": ["json", "xml"],
                    "concurrent_uploads": 3,
                }
            )

        return capabilities
