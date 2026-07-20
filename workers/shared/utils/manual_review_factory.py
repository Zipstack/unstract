"""Manual Review Service Factory.

Simplified plugin-aware factory for manual review services.
Uses complete service implementations from plugins when available,
falls back to minimal OSS null service otherwise.
"""

from typing import Any, Protocol

from client_plugin_registry import get_client_plugin, has_client_plugin
from unstract.core.data_models import WorkerFileData

from ..infrastructure.logging import WorkerLogger

logger = WorkerLogger.get_logger(__name__)

MANUAL_REVIEW_PLUGIN_NAME = "manual_review"


class ManualReviewServiceProtocol(Protocol):
    """Protocol defining the interface for manual review services."""

    def get_manual_review_config(
        self, workflow_id: str, total_files: int = 0
    ) -> dict[str, Any]:
        """Get manual review configuration for a workflow."""
        ...

    def calculate_q_file_no_list(
        self, config: dict[str, Any], total_files: int
    ) -> list[int]:
        """Calculate file numbers for manual review queue."""
        ...

    def calculate_batch_decisions(
        self,
        batch: list[tuple[str, Any]],
        source_files: dict[str, Any],
        config: dict[str, Any],
    ) -> list[bool]:
        """Calculate manual review decisions for files in a batch."""
        ...

    def create_workflow_file_data_with_manual_review(
        self,
        worker_file_data: WorkerFileData,
        use_file_history: bool,
        total_files: int = 0,
    ) -> Any:
        """Create WorkerFileData with manual review configuration."""
        ...

    def get_workflow_util(self) -> Any:
        """Get WorkflowUtil instance for this service."""
        ...


class ManualReviewNullService:
    """Null implementation of manual review service for OSS compatibility."""

    def __init__(self, api_client: Any, organization_id: str):
        """Initialize null service."""
        self.api_client = api_client
        self.organization_id = organization_id
        logger.debug("Using ManualReviewNullService - manual review disabled in OSS")

    def get_manual_review_config(
        self, workflow_id: str, total_files: int = 0
    ) -> dict[str, Any]:
        """Return default config indicating no manual review."""
        return {
            "review_required": False,
            "review_percentage": 0,
            "rule_logic": None,
            "rule_json": None,
            "q_file_no_list": [],
            "file_decisions": [],
        }

    def calculate_q_file_no_list(
        self, config: dict[str, Any], total_files: int
    ) -> list[int]:
        """Return empty list for OSS."""
        return []

    def calculate_batch_decisions(
        self,
        batch: list[tuple[str, Any]],
        source_files: dict[str, Any],
        config: dict[str, Any],
    ) -> list[bool]:
        """Return all False for OSS."""
        return [False] * len(batch)

    def create_workflow_file_data_with_manual_review(
        self,
        worker_file_data: WorkerFileData,
        use_file_history: bool,
        total_files: int = 0,
    ) -> WorkerFileData:
        """Create WorkerFileData without manual review for OSS."""
        worker_file_data.manual_review_config = self.get_manual_review_config(
            worker_file_data.workflow_id, total_files
        )
        worker_file_data.use_file_history = False
        worker_file_data.q_file_no_list = []
        return worker_file_data

    def get_workflow_util(self) -> Any:
        """Get WorkflowUtil instance (returns null implementation for OSS)."""

        # Return a simple null implementation for OSS
        class WorkflowUtilNull:
            @staticmethod
            def add_file_destination_filehash(file_number, q_file_no_list, file_hash):
                # OSS: No manual review processing, return file_hash unchanged
                return file_hash

            @staticmethod
            def get_q_no_list(workflow, total_files):
                # OSS: No manual review queue
                return None

            @staticmethod
            def validate_rule_engine(
                result,
                workflow_id,
                file_destination,
                is_manual_review_required,
                rule_type="DB",
            ):
                # OSS: No rule validation
                return False

            # Backward compatibility alias
            @staticmethod
            def validate_db_rule(
                result, workflow_id, file_destination, is_manual_review_required
            ):
                # OSS: No rule validation
                return False

            @staticmethod
            def has_api_rules(workflow):
                # OSS: No API rules support
                return False

            @staticmethod
            def get_hitl_ttl_seconds(workflow):
                # OSS: No TTL restrictions
                return None

        return WorkflowUtilNull()


class ManualReviewServiceFactory:
    """Plugin-aware factory for manual review services."""

    @staticmethod
    def create_service(
        api_client: Any, organization_id: str
    ) -> ManualReviewServiceProtocol:
        """Create manual review service using plugins when available.

        Args:
            api_client: Internal API client
            organization_id: Organization ID

        Returns:
            Enhanced service if plugin available, null service otherwise
        """
        # Try to get enhanced service from plugin first
        enhanced_service = ManualReviewServiceFactory._try_plugin_service(
            api_client, organization_id
        )

        if enhanced_service:
            logger.debug("Using enhanced manual review service from plugin")
            return enhanced_service

        # Fall back to OSS null service
        logger.debug("Using OSS null manual review service")
        return ManualReviewNullService(api_client, organization_id)

    @staticmethod
    def _try_plugin_service(
        api_client: Any, organization_id: str
    ) -> ManualReviewServiceProtocol | None:
        """Try to create enhanced service from plugins."""
        try:
            # Check for manual review service plugin
            if has_client_plugin(MANUAL_REVIEW_PLUGIN_NAME):
                service_plugin = get_client_plugin(
                    MANUAL_REVIEW_PLUGIN_NAME, api_client.config
                )
                if service_plugin:
                    # Set organization context on the service
                    service_plugin.set_organization_context(organization_id)

                    # Create enhanced service with WorkflowUtil access
                    enhanced_service = ManualReviewEnhancedService(
                        service_plugin, api_client, organization_id
                    )
                    return enhanced_service

            return None

        except Exception as e:
            logger.debug(f"Plugin service creation failed: {e}")
            return None


class ManualReviewEnhancedService:
    """Enhanced manual review service with plugin-based WorkflowUtil access."""

    def __init__(self, service_plugin: Any, api_client: Any, organization_id: str):
        """Initialize enhanced service with plugin access."""
        self.service_plugin = service_plugin
        self.api_client = api_client
        self.organization_id = organization_id
        self._workflow_util = None

    def get_manual_review_config(
        self, workflow_id: str, total_files: int = 0
    ) -> dict[str, Any]:
        """Delegate to plugin service."""
        if hasattr(self.service_plugin, "get_manual_review_config"):
            return self.service_plugin.get_manual_review_config(workflow_id, total_files)
        return {}

    def calculate_q_file_no_list(
        self, config: dict[str, Any], total_files: int
    ) -> list[int]:
        """Delegate to plugin service."""
        if hasattr(self.service_plugin, "calculate_q_file_no_list"):
            return self.service_plugin.calculate_q_file_no_list(config, total_files)
        return []

    def calculate_batch_decisions(
        self,
        batch: list[tuple[str, Any]],
        source_files: dict[str, Any],
        config: dict[str, Any],
    ) -> list[bool]:
        """Delegate to plugin service."""
        if hasattr(self.service_plugin, "calculate_batch_decisions"):
            return self.service_plugin.calculate_batch_decisions(
                batch, source_files, config
            )
        return [False] * len(batch)

    def create_workflow_file_data_with_manual_review(
        self,
        worker_file_data: WorkerFileData,
        use_file_history: bool,
        total_files: int = 0,
    ) -> WorkerFileData:
        """Delegate to plugin service."""
        if hasattr(self.service_plugin, "create_workflow_file_data_with_manual_review"):
            return self.service_plugin.create_workflow_file_data_with_manual_review(
                worker_file_data,
                use_file_history,
                total_files,
            )
        worker_file_data.manual_review_config = self.get_manual_review_config(
            worker_file_data.workflow_id, total_files
        )
        worker_file_data.use_file_history = False
        worker_file_data.q_file_no_list = []
        return worker_file_data

    def get_workflow_util(self) -> Any:
        """Get WorkflowUtil instance from plugin."""
        if self._workflow_util is None:
            # Try to get WorkflowUtil from the plugin service's components
            try:
                # Check if the service plugin has a get_workflow_util method
                if hasattr(self.service_plugin, "get_workflow_util"):
                    self._workflow_util = self.service_plugin.get_workflow_util()
                    logger.debug("Using WorkflowUtil from service plugin method")
                else:
                    # Try to get WorkflowUtil from plugin components
                    try:
                        from plugins.manual_review import ManualReviewWorkflowUtil

                        self._workflow_util = ManualReviewWorkflowUtil(
                            self.api_client.config
                        )
                        logger.debug(
                            "Using enterprise ManualReviewWorkflowUtil from plugin import"
                        )
                    except ImportError:
                        logger.debug(
                            "Plugin WorkflowUtil not available via import, using null implementation"
                        )
                        self._workflow_util = self._create_null_workflow_util()
            except Exception as e:
                logger.debug(f"Failed to get WorkflowUtil from plugin: {e}")
                self._workflow_util = self._create_null_workflow_util()

        return self._workflow_util

    def _create_null_workflow_util(self):
        """Create null WorkflowUtil implementation."""

        class WorkflowUtilNull:
            @staticmethod
            def add_file_destination_filehash(file_number, q_file_no_list, file_hash):
                return file_hash

            @staticmethod
            def get_q_no_list(workflow, total_files):
                return None

            @staticmethod
            def validate_rule_engine(
                result,
                workflow_id,
                file_destination,
                is_manual_review_required,
                rule_type="DB",
            ):
                return False

            @staticmethod
            def validate_rule_engine_with_reason(
                result,
                workflow_id,
                file_destination,
                is_manual_review_required,
                rule_type="DB",
            ):
                return {"matched": False, "reason": "HITL plugin not available"}

            # Backward compatibility alias
            @staticmethod
            def validate_db_rule(
                result, workflow_id, file_destination, is_manual_review_required
            ):
                return False

            @staticmethod
            def has_api_rules(workflow):
                return False

            @staticmethod
            def get_hitl_ttl_seconds(workflow):
                return None

        return WorkflowUtilNull()


# Simplified direct access functions
def get_manual_review_workflow_util(api_client: Any, organization_id: str) -> Any | None:
    """Get WorkflowUtil directly via plugin registry (simplified access).

    This eliminates the service layer for direct WorkflowUtil access.

    Args:
        api_client: Internal API client
        organization_id: Organization ID

    Returns:
        ManualReviewWorkflowUtil if plugin available, null implementation otherwise
    """
    try:
        if has_client_plugin(MANUAL_REVIEW_PLUGIN_NAME):
            # Get WorkflowUtil directly from plugin registry
            workflow_util = get_client_plugin(
                MANUAL_REVIEW_PLUGIN_NAME, api_client.config
            )
            if workflow_util:
                # Set organization context
                workflow_util.organization_id = organization_id
                workflow_util.client.set_organization_context(organization_id)
                return workflow_util

        return _create_null_workflow_util()

    except Exception as e:
        logger.debug(f"Failed to get WorkflowUtil from plugin: {e}")
        return _create_null_workflow_util()


def has_manual_review_plugin():
    return has_client_plugin(MANUAL_REVIEW_PLUGIN_NAME)


def _create_null_workflow_util():
    """Create null WorkflowUtil implementation for OSS compatibility."""

    class WorkflowUtilNull:
        def __init__(self):
            self.organization_id = None

        @staticmethod
        def add_file_destination_filehash(file_number, q_file_no_list, file_hash):
            return file_hash

        @staticmethod
        def get_q_no_list(workflow, total_files):
            return None

        @staticmethod
        def validate_rule_engine(
            result,
            workflow_id,
            file_destination,
            is_manual_review_required,
            rule_type="DB",
        ):
            return False

        @staticmethod
        def validate_rule_engine_with_reason(
            result,
            workflow_id,
            file_destination,
            is_manual_review_required,
            rule_type="DB",
        ):
            return {"matched": False, "reason": "HITL plugin not available"}

        # Backward compatibility alias
        @staticmethod
        def validate_db_rule(
            result, workflow_id, file_destination, is_manual_review_required
        ):
            return False

        @staticmethod
        def has_api_rules(workflow):
            return False

        def create_workflow_file_data_with_manual_review(
            self,
            worker_file_data: WorkerFileData,
            use_file_history,
            total_files=0,
        ):
            """Create workflow file data with manual review."""
            worker_file_data.manual_review_config = self.get_manual_review_config(
                worker_file_data.workflow_id, total_files
            )
            worker_file_data.use_file_history = False
            worker_file_data.q_file_no_list = []
            return worker_file_data

        def calculate_batch_decisions(self, batch, source_files, config):
            return [False] * len(batch)

        def enqueue_manual_review(self, *args, **kwargs):
            return

        def get_hitl_ttl_seconds(self, *args, **kwargs):
            return None

        def get_manual_review_config(self, workflow_id, total_files):
            return {}

    return WorkflowUtilNull()


# Legacy compatibility function
def get_manual_review_service(
    api_client: Any, organization_id: str
) -> ManualReviewServiceProtocol:
    """Legacy function for backward compatibility.

    This maintains compatibility while internally using the simplified pattern.
    """
    # Return a wrapper that delegates to WorkflowUtil
    workflow_util = get_manual_review_workflow_util(api_client, organization_id)

    class LegacyServiceWrapper:
        def __init__(self, workflow_util: Any | None):
            self.workflow_util = workflow_util

        def get_workflow_util(self):
            return self.workflow_util

        def create_workflow_file_data_with_manual_review(self, *args, **kwargs):
            return self.workflow_util.create_workflow_file_data_with_manual_review(
                *args, **kwargs
            )

        def calculate_batch_decisions(self, *args, **kwargs):
            return self.workflow_util.calculate_batch_decisions(*args, **kwargs)

    return LegacyServiceWrapper(workflow_util)
