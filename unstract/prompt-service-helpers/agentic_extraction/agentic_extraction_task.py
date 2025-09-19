"""Celery task for agentic data extraction using Autogen GraphFlow.
This task takes the generated digraph and executes the multi-agent extraction workflow.
"""

import json
import logging
from typing import Any

# Autogen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from celery import shared_task

from .agent_factory import AgentFactory
from .tools.rag_tool import RAGTool

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="execute_agentic_extraction")
def execute_agentic_extraction(
    self,
    digraph_output: dict[str, Any],
    answer_prompt_payload: dict[str, Any],
    doc_id: str,
    extraction_task: str | None = None,
    platform_key: str | None = None,
) -> dict[str, Any]:
    """Execute agentic data extraction using Autogen GraphFlow with answer_prompt format.

    Args:
        digraph_output: Output from digraph generation containing graph structure
        answer_prompt_payload: Answer prompt payload with outputs and tool_settings
        doc_id: Document ID for RAG access
        extraction_task: Custom extraction task description
        platform_key: Platform API key for SDK operations

    Returns:
        Dict containing:
            - final_output: Final extracted data
            - agent_results: Individual agent results
            - execution_metadata: Execution details
            - performance_metrics: Performance information
    """
    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting agentic data extraction")

    try:
        # Step 1: Initialize RAG tool
        rag_tool = RAGTool(doc_id=doc_id)

        # Step 2: Create agent factory with RAG tool
        agent_factory = AgentFactory(rag_tool=rag_tool)

        # Step 3: Recreate the GraphFlow from digraph output
        graph_flow = recreate_graph_flow_from_digraph(
            digraph_output, agent_factory, extraction_spec
        )

        # Step 4: Define extraction task
        if not extraction_task:
            fields = extraction_spec.get("fields", [])
            field_names = [f.get("name", "") for f in fields]
            extraction_task = f"""
            Extract the following fields from the document:
            {', '.join(field_names)}

            Document ID: {doc_id}

            Each agent should:
            1. Focus on their assigned field(s)
            2. Use available tools (RAG, Calculator, String operations) as needed
            3. Provide accurate and complete extractions
            4. Pass results to the next agent in the workflow

            Final output should be a structured JSON with all extracted fields.
            """

        # Step 5: Execute the GraphFlow
        logger.info(
            f"[Task {task_id}] Executing GraphFlow with {len(graph_flow.participants)} agents"
        )
        execution_results = execute_graph_flow_team(graph_flow, extraction_task)

        # Step 6: Process and format results
        final_output = process_execution_results(execution_results, extraction_spec)

        # Step 7: Calculate performance metrics
        performance_metrics = calculate_performance_metrics(execution_results, task_id)

        # Prepare final result
        result = {
            "final_output": final_output,
            "agent_results": execution_results.get("all_results", {}),
            "execution_metadata": {
                "task_id": task_id,
                "doc_id": doc_id,
                "agent_count": len(graph_flow.participants),
                "execution_status": execution_results.get("execution_status", "unknown"),
            },
            "performance_metrics": performance_metrics,
        }

        logger.info(f"[Task {task_id}] Agentic extraction completed successfully")
        return result

    except Exception as e:
        logger.error(f"[Task {task_id}] Error in agentic extraction: {str(e)}")
        raise


def recreate_graph_flow_from_digraph(
    digraph_output: dict[str, Any],
    agent_factory: AgentFactory,
    extraction_spec: dict[str, Any],
) -> GraphFlow:
    """Recreate GraphFlow from digraph generation output.

    Args:
        digraph_output: Output from digraph generation
        agent_factory: Factory for creating agents with tools
        extraction_spec: Original extraction specification

    Returns:
        GraphFlow instance ready for execution
    """
    # Extract agent configurations from digraph output
    agent_configs = digraph_output.get("agents", [])
    execution_plan = digraph_output.get("execution_plan", {})

    # Create new DiGraphBuilder
    builder = DiGraphBuilder()

    # Create agents using the factory
    agents = []
    for agent_config in agent_configs:
        agent = agent_factory.create_agent(agent_config, extraction_spec)
        agents.append(agent)
        builder.add_node(agent)

    # Recreate edges based on execution plan
    recreate_edges_from_plan(builder, agents, execution_plan, extraction_spec)

    # Build graph and create GraphFlow
    graph = builder.build()
    graph_flow = GraphFlow(participants=builder.get_participants(), graph=graph)

    return graph_flow


def recreate_edges_from_plan(
    builder: DiGraphBuilder,
    agents: list[AssistantAgent],
    execution_plan: dict[str, Any],
    extraction_spec: dict[str, Any],
) -> None:
    """Recreate edges in the DiGraphBuilder based on execution plan.

    Args:
        builder: DiGraphBuilder instance
        agents: List of created agents
        execution_plan: Execution plan from digraph generation
        extraction_spec: Original extraction specification
    """
    # Create agent lookup
    agent_map = {agent.name: agent for agent in agents}

    # Get dependencies from extraction spec
    dependencies = extraction_spec.get("dependencies", {})
    tool_settings = extraction_spec.get("tool_settings", {})

    # Add dependency edges
    for field_name, dep_fields in dependencies.items():
        target_agent = None
        for agent in agents:
            if field_name in agent.name:
                target_agent = agent
                break

        if target_agent:
            for dep_field in dep_fields:
                source_agent = None
                for agent in agents:
                    if dep_field in agent.name:
                        source_agent = agent
                        break

                if source_agent:
                    builder.add_edge(source_agent, target_agent)

    # Add workflow edges (extraction → challenger → collation)
    challenger_agent = None
    collation_agent = None

    for agent in agents:
        if "challenger_agent" in agent.name:
            challenger_agent = agent
        elif "data_collation_agent" in agent.name:
            collation_agent = agent

    # Connect extraction agents to challenger or collation
    if challenger_agent and tool_settings.get("enable_challenge", False):
        # All extraction agents → challenger
        for agent in agents:
            if (
                agent != challenger_agent
                and agent != collation_agent
                and "extraction_agent" in agent.name
            ):
                builder.add_edge(agent, challenger_agent)

        # Challenger → collation with approval condition
        if collation_agent:
            builder.add_edge(
                challenger_agent,
                collation_agent,
                condition=lambda msg: (
                    "approved" in msg.content.lower()
                    or "validated" in msg.content.lower()
                    or "accepted" in msg.content.lower()
                ),
            )
    elif collation_agent:
        # Direct extraction agents → collation
        for agent in agents:
            if agent != collation_agent and "extraction_agent" in agent.name:
                builder.add_edge(agent, collation_agent)


def execute_graph_flow_team(
    graph_flow: GraphFlow,
    extraction_task: str,
) -> dict[str, Any]:
    """Execute the GraphFlow team and collect results.

    Args:
        graph_flow: GraphFlow instance to execute
        extraction_task: Task description for the team

    Returns:
        Execution results
    """
    results = {}
    final_output = None
    events = []

    try:
        logger.info("Starting GraphFlow execution...")

        # Execute the GraphFlow
        stream = graph_flow.run_stream(task=extraction_task)

        for event in stream:
            # Log event details
            logger.info(f"Event: {event.type}, Agent: {event.source}")

            # Store event for analysis
            events.append(
                {
                    "type": event.type,
                    "source": event.source,
                    "content": event.content[:200] if hasattr(event, "content") else None,
                    "timestamp": str(event.timestamp)
                    if hasattr(event, "timestamp")
                    else None,
                }
            )

            # Store agent results
            if hasattr(event, "content") and event.content:
                results[event.source] = event.content

                # Check for final collation result
                if event.source == "data_collation_agent":
                    try:
                        final_output = json.loads(event.content)
                    except json.JSONDecodeError:
                        final_output = event.content

        execution_status = "completed" if final_output else "incomplete"

    except Exception as e:
        logger.error(f"Error during GraphFlow execution: {str(e)}")
        execution_status = "error"
        final_output = None

    return {
        "final_output": final_output,
        "all_results": results,
        "execution_status": execution_status,
        "events": events,
    }


def process_execution_results(
    execution_results: dict[str, Any],
    extraction_spec: dict[str, Any],
) -> dict[str, Any]:
    """Process and validate execution results.

    Args:
        execution_results: Raw execution results from GraphFlow
        extraction_spec: Original extraction specification

    Returns:
        Processed final output
    """
    final_output = execution_results.get("final_output")

    if not final_output:
        # Try to construct output from individual agent results
        agent_results = execution_results.get("all_results", {})
        fields = extraction_spec.get("fields", [])

        constructed_output = {}
        for field in fields:
            field_name = field.get("name", "")
            # Look for results from agents that handled this field
            for agent_name, result in agent_results.items():
                if field_name in agent_name:
                    try:
                        # Try to extract structured data
                        if isinstance(result, str) and result.strip().startswith("{"):
                            parsed_result = json.loads(result)
                            if field_name in parsed_result:
                                constructed_output[field_name] = parsed_result[field_name]
                        else:
                            constructed_output[field_name] = result
                    except (json.JSONDecodeError, KeyError):
                        constructed_output[field_name] = result
                    break

        if constructed_output:
            final_output = constructed_output

    return final_output or {}


def calculate_performance_metrics(
    execution_results: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    """Calculate performance metrics for the execution.

    Args:
        execution_results: Execution results
        task_id: Task identifier

    Returns:
        Performance metrics
    """
    events = execution_results.get("events", [])
    agent_results = execution_results.get("all_results", {})

    return {
        "total_events": len(events),
        "agents_executed": len(agent_results),
        "execution_status": execution_results.get("execution_status", "unknown"),
        "has_final_output": execution_results.get("final_output") is not None,
        "task_id": task_id,
    }
