"""
Utility for executing Autogen GraphFlow instances.
This module provides functions to execute the generated GraphFlow and get results.
"""

import json
import logging
from typing import Any, Dict, Optional

from autogen_agentchat.teams import GraphFlow

logger = logging.getLogger(__name__)


def execute_extraction_workflow(
    graph_flow_data: Dict[str, Any],
    task_description: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute an extraction workflow using GraphFlow.

    Args:
        graph_flow_data: Serialized GraphFlow data from digraph generation
        task_description: Custom task description (optional)
        doc_id: Document ID for context (optional)

    Returns:
        Extraction results including final output and intermediate results
    """
    try:
        # Deserialize the GraphFlow (this would need to be implemented based on
        # how Autogen handles serialization/deserialization)
        # For now, this is a placeholder showing the intended structure

        # Default task if not provided
        if not task_description:
            task_description = f"""Extract all specified fields from the document accurately.
            Document ID: {doc_id if doc_id else 'Not specified'}
            Follow the workflow defined in the graph to ensure proper data extraction.
            Each agent should focus on their specific role and pass results to the next agent."""

        logger.info(f"Starting extraction workflow with {len(graph_flow_data.get('agents', []))} agents")

        # This would execute the actual GraphFlow
        # graph_flow = deserialize_graph_flow(graph_flow_data)
        # results = execute_graph_flow(graph_flow, task_description)

        # Placeholder results structure
        results = {
            "final_output": {},
            "all_results": {},
            "execution_status": "not_implemented",
            "message": "GraphFlow execution needs to be implemented based on Autogen's serialization format"
        }

        return results

    except Exception as e:
        logger.error(f"Error executing extraction workflow: {str(e)}")
        return {
            "final_output": None,
            "all_results": {},
            "execution_status": "error",
            "error": str(e)
        }


def validate_graph_flow_data(graph_flow_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate GraphFlow data structure.

    Args:
        graph_flow_data: GraphFlow data to validate

    Returns:
        Validation results
    """
    issues = []
    warnings = []

    # Check required fields
    required_fields = ["graph_flow", "agents", "graph", "metadata"]
    for field in required_fields:
        if field not in graph_flow_data:
            issues.append(f"Missing required field: {field}")

    # Check agents
    agents = graph_flow_data.get("agents", [])
    if not agents:
        issues.append("No agents found in GraphFlow data")

    for agent in agents:
        if not isinstance(agent, dict):
            issues.append(f"Invalid agent format: {agent}")
            continue

        if "name" not in agent:
            issues.append("Agent missing name field")

    # Check for collation agent
    has_collation = any(
        "data_collation_agent" in agent.get("name", "")
        for agent in agents
    )
    if not has_collation:
        warnings.append("No collation agent found - results may not be properly formatted")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "agent_count": len(agents),
    }