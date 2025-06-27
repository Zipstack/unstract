import json
import logging
import operator
import random
from typing import Any, Optional

from pluggable_apps.manual_review_v2.helper import get_db_rules_by_workflow_id
from workflow_manager.endpoint_v2.dto import FileHash
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.workflow_v2.constants import ResultKeys
from workflow_manager.workflow_v2.enums import RuleLogic
from workflow_manager.workflow_v2.models.workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowUtil:
    """A utility class for handling workflow-related operations, including file
    selection based on a percentage rule and modifying file destination based
    on certain criteria."""

    @staticmethod
    def _mrq_files(
        percentage: float,
        n: int,
    ) -> Any:
        """Selects a random subset of file indices based on the specified
        percentage.

        Args:
            percentage (float): The percentage of files to be selected.
            n (int): The total number of files.

        Returns:
            Any: A set containing the selected file indices.
        """
        num_to_select = max(1, int(n * (percentage / 100)))
        return set(random.sample(range(1, n+1), num_to_select))

    @classmethod
    def get_q_no_list(cls, workflow: Workflow, total_files: int) -> Any:
        """Retrieves a list of file indices to be manually reviewed based on
        the workflow's percentage rule.

        Args:
            workflow (Workflow): The workflow instance.
            total_files (int): The total number of files.

        Returns:
            Any: A set of file indices to be reviewed, or None if no files are
            to be reviewed.
        """
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
        """Modifies the file destination in the FileHash object if the file
        index is in the list of files to be reviewed.

        Args:
            index (int): The index of the file.
            q_file_no_list (Any): The list of file indices to be reviewed.
            file_hash (FileHash): The FileHash object representing the file.

        Returns:
            FileHash: The modified or unmodified FileHash object.
        """
        if q_file_no_list is None:
            return file_hash
        if index in q_file_no_list:
            file_hash.file_destination = (
                WorkflowEndpoint.ConnectionType.MANUALREVIEW
            )
        return file_hash

    @staticmethod
    def _check_confidence(field_entries, threshold):
        # Check if any confidence value meets or exceeds the threshold
        meets_threshold = any(
            float(entry.get("confidence", 0)) * 100 >= threshold
            for entries in field_entries
            if entries  # Skip empty entries
            for entry in entries
            if "confidence" in entry  # Check for valid confidence key
        )
        return meets_threshold

    @classmethod
    def _evaluate_rule(
        cls, rule: dict[str, Any], context: dict[str, Any], conjunction: str
    ) -> bool:
        # Mapping of operators to Python equivalents
        operator_map = {
            "less": operator.lt,
            "greater": operator.gt,
            "equal": operator.eq,
            "not_equal": operator.ne,
            "less_or_equal": operator.le,
            "greater_or_equal": operator.ge,
            "starts_with": lambda field, value: field.startswith(value),
            "ends_with": lambda field, value: field.endswith(value),
            "like": lambda field, value: value in field,
            "not_like": lambda field, value: value not in field,
        }
        field = rule["properties"]["field"]
        operator_name = rule["properties"]["operator"]
        # Support all types of operators in up coming versions
        value = rule["properties"]["value"][0]
        all_values = rule["properties"]["value"]
        # Convert dot notation in field to dictionary access
        keys = field.split(".")
        if keys[0] == "filterByValue":
            field_value = context.get(ResultKeys.OUTPUT, {}).get(keys[1], {})
        elif keys[0] == "jsonField":
            # Get the base field from the context
            field_value = context.get(ResultKeys.OUTPUT, {}).get(keys[1], {})
            
            # Handle the special cases for "key" and "value"
            if keys[-1] == "key":
                return operator_map["equal"](value in field_value, True)
            elif keys[-1] == "value":
                current_value = field_value
                for key in keys[2:-1]:  # Skip "jsonField" and "value"
                    if key in current_value:
                        current_value = current_value.get(key, {})
                    else:
                        return False  # Key path doesn't exist
                target_key = value  # The key we're looking for is the value in our rule
                # Check if the value for this key matches our expected value
                if target_key in current_value:
                    return operator_map[operator_name](current_value[target_key], value)
                
                # If we can't determine the specific key-value pair, fall back to direct comparison
                # This handles cases where we're directly comparing a value
                for key, val in current_value.items():
                    if operator_map[operator_name](val, value):
                        return True
                return False
            else:
                # For direct field access (not key/value)
                # Traverse the remaining path
                for key in keys[2:]:  # Skip "jsonField" and the field name
                    if isinstance(field_value, dict) and key in field_value:
                        field_value = field_value.get(key, {})
                    else:
                        return False  # Path doesn't exist
                
                # Compare the final value
                return operator_map[operator_name](field_value, value)
        elif keys[0] == "confidence":
            # Get confidence_data from the result
            confidence_data = context.get(ResultKeys.METADATA, {}).get(
                ResultKeys.CONFIDENCE_DATA, {}
            )
            field_entries = confidence_data.get(keys[1])
            threshold = value
            meets_threshold = cls._check_confidence(field_entries, threshold)
            return meets_threshold
        else:
            if conjunction == "and":
                return True
            elif conjunction == "or":
                return False
        try:
            # if the extracted value type is bool then converting it to str
            # and check
            if type(field_value) is bool:
                field_value = str(field_value).lower()
                value = str(value).lower()
            return operator_map[operator_name](field_value, value)
        except Exception as e:
            logger.error(f"Error evaluating rule: {e}")
            return False

    @classmethod
    def _evaluate_group(
        cls, group: dict[str, Any], context: dict[str, Any]
    ) -> bool:
        """Evaluates a group of rules or nested groups.

        Args:
            group (Dict[str, Any]): The group of rules or nested groups to be evaluated.
            context (Dict[str, Any]): The context containing values to be checked.

        Returns:
            bool: True if the group conditions are met, False otherwise.
        """
        conjunction = (
            group["properties"].get("conjunction", "and").lower()
        )  # AND/OR
        negate = group["properties"].get("not", False)

        results = []
        for child in group["children1"]:
            if child["type"] == "rule":
                results.append(cls._evaluate_rule(child, context, conjunction))
            elif child["type"] in ["group", "rule_group"]:
                results.append(cls._evaluate_group(child, context))

        # Combine results based on the conjunction
        if conjunction == "and":
            result = all(results)
        elif conjunction == "or":
            result = any(results)
        else:
            raise ValueError(f"Unknown conjunction: {conjunction}")

        # Apply negation if needed
        return not result if negate else result

    @classmethod
    def validate_db_rule(
        cls,
        result: Optional[Any],
        workflow_id: str,
        file_destination: Optional[tuple[str, str]],
    ) -> bool:
        """Check if the field_key from DBRules exists in the confidence_data of
        the result according to the rule logic (AND/OR).

        Args:
            result (Optional[Any]): The result dictionary
            containing confidence_data.
            workflow_id (str): The ID of the workflow to retrieve the rules.
            file_destination (Optional[tuple[str, str]]): The destination of
            the file (e.g., MANUALREVIEW or other).

        Returns:
            bool: True if the field_key conditions are met based on rule logic
            and file destination.
        """
        # Check each filter condition
        conditions_met = []
        if file_destination == WorkflowEndpoint.ConnectionType.MANUALREVIEW:
            conditions_met.append(True)
        else:
            conditions_met.append(False)

        # Get the DBRules instance using the workflow_id
        db_rule = get_db_rules_by_workflow_id(workflow=workflow_id)

        rule_string = db_rule.rule_string if db_rule else None

        # Get the rule logic (AND/OR)
        rule_logic = db_rule.rule_logic if db_rule else None
        if not rule_string:
            conditions_met.append(False)
        else:
            rule_json = json.loads(db_rule.rule_json)
            status = cls._evaluate_group(rule_json, result)
            conditions_met.append(status)
        # Apply rule logic:
        if rule_logic == RuleLogic.AND:
            # All conditions must be met
            return all(conditions_met)
        
        # If rule logic is 'OR', check if any condition is met
        return any(conditions_met)
