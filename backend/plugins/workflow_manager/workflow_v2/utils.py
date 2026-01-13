"""Workflow utility functions.

This module provides utility functions for workflow operations, including
file selection for manual review and rule validation. Extended features
are loaded from pluggable_apps.manual_review_v2 if available.
"""

import logging
import random
from typing import Any

from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowUtil:
    """Utility class for workflow operations.

    Extended functionality for manual review is loaded from
    pluggable_apps.manual_review_v2 if available.
    """

    @staticmethod
    def _mrq_files(
        percentage: float,
        n: int,
    ) -> Any:
        """Select a subset of files based on a given percentage.

        Args:
            percentage (float): The percentage of files to select.
            n (int): The total number of files.

        Returns:
            A set of file indices, or None if manual_review_v2 is not available.
        """
        num_to_select = max(1, int(n * (percentage / 100)))
        return set(random.sample(range(1, n + 1), num_to_select))

    @classmethod
    def get_q_no_list(cls, workflow: Workflow, total_files: int) -> Any:
        """Retrieve a list of files to be reviewed based on workflow rules.

        Args:
            workflow (Workflow): The workflow instance.
            total_files (int): The total number of files.

        Returns:
            A set of file indices to be reviewed, or None.
        """
        try:
            from pluggable_apps.manual_review_v2.helper import get_db_rules_by_workflow_id
        except ImportError:
            return None

        q_db_rules = get_db_rules_by_workflow_id(workflow=workflow)
        if q_db_rules and q_db_rules.percentage > 0:
            return cls._mrq_files(q_db_rules.percentage, total_files)
        return None

    @staticmethod
    def add_file_destination_filehash(
        index: int,
        q_file_no_list: Any,
        file_hash: FileHash,
    ) -> FileHash:
        """Update the file destination if the file index is marked for review.

        Args:
            index (int): The index of the file.
            q_file_no_list: The list of file indices to be reviewed.
            file_hash (FileHash): The FileHash object.

        Returns:
            FileHash: The potentially updated FileHash object.
        """
        if q_file_no_list is None:
            return file_hash

        try:
            from workflow_manager.endpoint_v2.models import WorkflowEndpoint
        except ImportError:
            return file_hash

        if index in q_file_no_list:
            file_hash.file_destination = WorkflowEndpoint.ConnectionType.MANUALREVIEW
        return file_hash

    @staticmethod
    def validate_rule_engine(
        result: Any | None,
        workflow: Workflow,
        file_destination: tuple[str, str] | None,
        rule_type: str = "DB",
    ) -> bool:
        """Check the rule engine for manual review qualification.

        Args:
            result: The result dictionary containing confidence_data.
            workflow (Workflow): The workflow to retrieve the rules.
            file_destination: The destination of the file.
            rule_type (str): Rule type - "DB" or "API".

        Returns:
            bool: True if conditions are met for manual review.
        """
        try:
            from plugins.workflow_manager.workflow_v2.rule_engine import (
                RuleEngineValidator,
            )

            return RuleEngineValidator.validate(
                result, workflow, file_destination, rule_type
            )
        except ImportError:
            pass

        return False

    @staticmethod
    def validate_db_rule(
        result: Any | None,
        workflow: Workflow,
        file_destination: tuple[str, str] | None,
    ) -> bool:
        """Backward compatible method to check db rules.

        Deprecated: Use validate_rule_engine instead.
        """
        return WorkflowUtil.validate_rule_engine(
            result, workflow, file_destination, rule_type="DB"
        )

    @staticmethod
    def has_api_rules(workflow: Workflow) -> bool:
        """Check if API rules are configured for a workflow.

        Args:
            workflow (Workflow): The workflow to check.

        Returns:
            bool: True if API rules exist for this workflow.
        """
        try:
            from pluggable_apps.manual_review_v2.helper import get_db_rules_by_workflow_id

            db_rule = get_db_rules_by_workflow_id(workflow=workflow)
            return db_rule is not None and db_rule.rule_string is not None
        except ImportError:
            pass

        return False

    @staticmethod
    def get_hitl_ttl_seconds(workflow: Workflow) -> int | None:
        """Get TTL in seconds for HITL settings for a workflow.

        Args:
            workflow (Workflow): The workflow to get HITL TTL settings for.

        Returns:
            int | None: TTL in seconds if set, None for unlimited TTL.
        """
        try:
            from pluggable_apps.manual_review_v2.helper import (
                get_hitl_ttl_seconds_by_workflow,
            )

            return get_hitl_ttl_seconds_by_workflow(workflow)
        except ImportError:
            pass

        return None
