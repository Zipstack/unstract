"""
Celery task for generating Autogen GraphFlow for sequential data extraction.
This task creates actual Autogen DiGraphBuilder instances and GraphFlow
to orchestrate extraction agents in a sequential/dependency-based execution pattern.

The implementation uses:
- autogen_agentchat.agents.AssistantAgent for individual extraction agents
- autogen_agentchat.teams.DiGraphBuilder to create directed graph structure
- autogen_agentchat.teams.GraphFlow for sequential team execution

This is designed for sequential team processing where agents execute in a specific
order based on field dependencies and workflow requirements.
"""

import json
import logging
from typing import Any, Dict, List, Optional
from celery import shared_task

# Autogen imports - using the correct components for sequential teams
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
# Note: For sequential team processing, we use DiGraphBuilder which creates a directed graph
# that can be executed by GraphFlow for proper sequential/dependency-based execution

from .spec_parser import ExtractionSpecParser

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="generate_extraction_digraph")
def generate_extraction_digraph(
    self,
    extraction_spec: Dict[str, Any],
    previous_stage_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate Autogen GraphFlow for data extraction.

    Args:
        extraction_spec: Data extraction specification containing:
            - outputs: List of fields to extract with prompts
            - tool_settings: Configuration for tools and agents
            - dependencies: Field dependencies (optional)
        previous_stage_output: Output from chunking/embedding stage containing:
            - doc_id: Document identifier for RAG access

    Returns:
        Dict containing:
            - graph_flow: Serialized GraphFlow object
            - agents: List of created agents
            - graph: DiGraph structure
            - execution_plan: Execution flow information
            - metadata: Additional information
    """

    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting Autogen digraph generation")

    try:
        # Step 1: Parse the extraction specification
        parser = ExtractionSpecParser()
        parsed_spec = parser.parse(extraction_spec)

        # Add doc_id from previous stage if available
        doc_id = None
        if previous_stage_output and "doc_id" in previous_stage_output:
            doc_id = previous_stage_output["doc_id"]
            logger.info(f"[Task {task_id}] Using doc_id: {doc_id}")

        # Step 2: Get field and agent information
        fields = parsed_spec.get("fields", [])
        required_agents = parsed_spec.get("required_agents", [])
        dependencies = parsed_spec.get("dependencies", {})

        # Step 3: Generate agent configurations using the parser
        agents = generate_agent_configs(
            fields=fields,
            required_agents=required_agents,
            tool_settings=parsed_spec.get("tool_settings", {}),
            parser=parser,
            doc_id=doc_id,
        )

        # Step 4: Create actual Autogen agents
        autogen_agents = create_autogen_agents(agents, doc_id)

        # Step 5: Create Autogen DiGraphBuilder for sequential team processing
        # DiGraphBuilder creates a directed graph that enforces execution order
        builder = DiGraphBuilder()

        # Add all agents as nodes to the DiGraphBuilder
        for agent in autogen_agents:
            builder.add_node(agent)

        # Step 6: Add edges to define sequential execution order based on dependencies
        add_edges_to_builder(builder, autogen_agents, dependencies, parsed_spec.get("tool_settings", {}))

        # Step 7: Build the directed graph using Autogen's DiGraphBuilder
        # This creates the actual graph structure that GraphFlow will execute
        graph = builder.build()

        # Step 8: Create GraphFlow with the built graph for sequential execution
        # GraphFlow will execute agents in the order defined by the directed graph
        graph_flow = GraphFlow(participants=builder.get_participants(), graph=graph)

        # Verify we're using proper Autogen components
        verify_autogen_components(builder, graph_flow)

        # Step 9: Create execution plan
        execution_plan = create_execution_plan(agents, dependencies)

        # Prepare result
        result = {
            "graph_flow": serialize_graph_flow(graph_flow),
            "agents": [serialize_agent(agent) for agent in autogen_agents],
            "graph": serialize_graph(graph),
            "execution_plan": execution_plan,
            "metadata": {
                "task_id": task_id,
                "total_agents": len(autogen_agents),
                "doc_id": doc_id,
                "extraction_spec": parsed_spec,
            }
        }

        logger.info(
            f"[Task {task_id}] Autogen digraph generated successfully with "
            f"{len(autogen_agents)} agents"
        )
        return result

    except Exception as e:
        logger.error(f"[Task {task_id}] Error generating Autogen digraph: {str(e)}")
        raise


def analyze_field_dependencies(
    fields: List[Dict[str, Any]],
    explicit_dependencies: Dict[str, List[str]]
) -> Dict[str, List[str]]:
    """
    Analyze dependencies between fields based on variable references.

    Args:
        fields: List of field specifications
        explicit_dependencies: Explicitly defined dependencies

    Returns:
        Dictionary mapping field names to their dependencies
    """
    dependencies = {}

    # Initialize with explicit dependencies
    for field_name, deps in explicit_dependencies.items():
        dependencies[field_name] = list(deps)

    # Analyze implicit dependencies from variable references
    for field in fields:
        field_name = field.get("name", "")
        prompt_text = field.get("prompt", "")

        # Find variable references in the prompt (e.g., {{other_field}})
        import re
        variable_pattern = r'\{\{(\w+)\}\}'
        referenced_fields = re.findall(variable_pattern, prompt_text)

        if field_name not in dependencies:
            dependencies[field_name] = []

        # Add referenced fields as dependencies
        for ref_field in referenced_fields:
            if ref_field != field_name and ref_field not in dependencies[field_name]:
                dependencies[field_name].append(ref_field)

    return dependencies


def generate_agent_configs(
    fields: List[Dict[str, Any]],
    required_agents: List[str],
    tool_settings: Dict[str, Any],
    parser: ExtractionSpecParser,
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate agent configurations based on required agents and fields.

    Args:
        fields: List of field specifications
        required_agents: List of required agent types
        tool_settings: Tool configuration settings
        parser: ExtractionSpecParser instance
        doc_id: Document ID for RAG access

    Returns:
        List of agent configurations
    """
    agents = []

    # Group fields by agent type
    fields_by_agent = {}
    for field in fields:
        agent_type = field.get("agent_type", "generic_data_extraction_agent")
        if agent_type not in fields_by_agent:
            fields_by_agent[agent_type] = []
        fields_by_agent[agent_type].append(field)

    # Create extraction agents
    for agent_type in required_agents:
        if agent_type in ["challenger_agent", "data_collation_agent"]:
            continue  # Handle these separately

        # Create one agent instance per field for this agent type
        if agent_type in fields_by_agent:
            for field in fields_by_agent[agent_type]:
                field_name = field.get("name", "")
                system_message = parser.create_agent_system_message(agent_type, field)

                agent_config = {
                    "name": f"{agent_type}_{field_name}",
                    "agent_type": "AssistantAgent",
                    "system_message": system_message,
                    "tools": parser.get_agent_config(agent_type).get("tools", []),
                    "field_config": {
                        "field_name": field_name,
                        "extraction_agent_type": agent_type,
                        "doc_id": doc_id,
                    }
                }
                agents.append(agent_config)

    # Add challenger agent if enabled
    if "challenger_agent" in required_agents:
        challenger_system_message = parser.create_agent_system_message("challenger_agent")
        challenger_agent = {
            "name": "challenger_agent",
            "agent_type": "AssistantAgent",
            "system_message": challenger_system_message,
            "tools": parser.get_agent_config("challenger_agent").get("tools", []),
            "field_config": {
                "agent_role": "challenger",
                "doc_id": doc_id,
            }
        }
        agents.append(challenger_agent)

    # Add collation agent (always needed)
    if "data_collation_agent" in required_agents:
        collation_system_message = parser.create_agent_system_message("data_collation_agent", all_fields=fields)
        collation_agent = {
            "name": "data_collation_agent",
            "agent_type": "AssistantAgent",
            "system_message": collation_system_message,
            "tools": parser.get_agent_config("data_collation_agent").get("tools", []),
            "field_config": {
                "agent_role": "collation",
                "output_fields": [f.get("name") for f in fields],
            }
        }
        agents.append(collation_agent)

    return agents


def determine_agent_config(
    field: Dict[str, Any],
    tool_settings: Dict[str, Any],
    doc_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Determine agent type and system message for a field.

    Args:
        field: Field specification
        tool_settings: Tool settings
        doc_id: Document ID for RAG

    Returns:
        Tuple of (agent_type, system_message)
    """
    field_name = field.get("name", "")
    prompt = field.get("prompt", "")
    field_type = field.get("type", "text").lower()

    # Determine if this is a table extraction
    if field_type == "table" or "table" in prompt.lower():
        agent_type = "AssistantAgent"
        system_message = f"""You are a table extraction specialist. Your task is to extract the field '{field_name}' from the document.

Field Description: {prompt}

Instructions:
1. Search for tabular data in the document that matches the field description
2. Extract the table data accurately, preserving structure
3. Format the output as requested
4. If you need context from the document, use the RAG tool to search for relevant information
5. Be precise and only extract what is explicitly requested

Tools available: calculator"""

    elif field_type in ["image", "chart", "diagram"] or any(
        keyword in prompt.lower() for keyword in ["image", "chart", "diagram", "visual"]
    ):
        agent_type = "AssistantAgent"
        system_message = f"""You are a visual content extraction specialist. Your task is to extract the field '{field_name}' from the document.

Field Description: {prompt}

Instructions:
1. Analyze visual elements in the document (charts, diagrams, images)
2. Extract the requested information from visual content
3. Provide accurate descriptions and data from visual elements
4. Use calculation tools if needed for data processing
5. Be thorough in your visual analysis

Tools available: calculator"""

    else:
        # Generic text extraction
        agent_type = "AssistantAgent"
        rag_instruction = "5. Use the RAG tool to search for relevant context if needed" if doc_id else "5. Work with the provided document content"

        system_message = f"""You are a data extraction specialist. Your task is to extract the field '{field_name}' from the document.

Field Description: {prompt}
Field Type: {field_type}
Required: {field.get('required', False)}

Instructions:
1. Carefully read and understand the field description
2. Search through the document for information matching this field
3. Extract only the specific information requested
4. Ensure accuracy and completeness
{rag_instruction}
6. If the information is not found, clearly state that it's not available

Tools available: {"rag, calculator" if doc_id else "calculator"}"""

    return agent_type, system_message


def create_challenger_system_message(fields: List[Dict[str, Any]], doc_id: Optional[str]) -> str:
    """Create system message for the challenger agent."""
    field_names = [f.get("name") for f in fields]
    required_fields = [f.get("name") for f in fields if f.get("required", False)]

    rag_instruction = "- Use RAG to verify information against the source document" if doc_id else "- Verify against the provided document content"

    return f"""You are a quality assurance specialist responsible for validating extracted data.

Your role:
1. Review all extracted field values from other agents
2. Challenge incorrect, incomplete, or inconsistent extractions
3. Verify that required fields are properly extracted
4. Check for logical consistency between related fields

Fields to validate: {', '.join(field_names)}
Required fields: {', '.join(required_fields)}

Validation approach:
- Check accuracy against source material
{rag_instruction}
- Ensure completeness for required fields
- Identify inconsistencies or errors
- Provide specific feedback for corrections

If you find issues, clearly state what needs to be corrected and why.
If extractions are accurate, approve them for final collation.

Tools available: {"rag, calculator" if doc_id else "calculator"}"""


def create_collation_system_message(fields: List[Dict[str, Any]]) -> str:
    """Create system message for the collation agent."""
    field_names = [f.get("name") for f in fields]

    return f"""You are a data collation specialist responsible for combining all extracted field values into the final output.

Your role:
1. Collect all validated field values from extraction agents
2. Resolve any remaining conflicts between extractions
3. Format the final output as a structured JSON object
4. Ensure all required fields are included
5. Apply any final formatting or transformations

Fields to collate: {', '.join(field_names)}

Output format:
{{
{', '.join([f'  "{name}": "extracted_value"' for name in field_names])}
}}

Instructions:
- Use the most recent validated values for each field
- If multiple values exist for a field, use your judgment to select the best one
- Ensure the output JSON is properly formatted
- Include null values for fields that couldn't be extracted

Tools available: string_operations"""


def generate_edge_configs(
    agents: List[Dict[str, Any]],
    dependencies: Dict[str, List[str]],
    tool_settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Generate edge configurations based on dependencies.

    Args:
        agents: List of agent configurations
        dependencies: Field dependencies
        tool_settings: Tool settings

    Returns:
        List of edge configurations
    """
    edges = []
    agent_map = {agent["field_config"].get("field_name"): agent["name"] for agent in agents if "field_name" in agent.get("field_config", {})}

    # Add dependency edges
    for field_name, dep_fields in dependencies.items():
        if field_name in agent_map:
            target_agent = agent_map[field_name]

            for dep_field in dep_fields:
                if dep_field in agent_map:
                    source_agent = agent_map[dep_field]

                    edge = {
                        "source": source_agent,
                        "target": target_agent,
                        "condition": None,  # No condition for dependency edges
                    }
                    edges.append(edge)

    # Add edges to challenger (if enabled)
    has_challenger = tool_settings.get("enable_challenge", False)
    if has_challenger:
        extraction_agents = [agent["name"] for agent in agents if agent.get("field_config", {}).get("agent_role") != "challenger" and agent.get("field_config", {}).get("agent_role") != "collation"]

        for agent_name in extraction_agents:
            edge = {
                "source": agent_name,
                "target": "challenger_agent",
                "condition": None,
            }
            edges.append(edge)

    # Add edges to collation
    if has_challenger:
        # Collation depends on challenger
        edge = {
            "source": "challenger_agent",
            "target": "collation_agent",
            "condition": 'lambda msg: "approved" in msg.content.lower() or "validated" in msg.content.lower()',
        }
        edges.append(edge)
    else:
        # Collation depends directly on extraction agents
        extraction_agents = [agent["name"] for agent in agents if agent.get("field_config", {}).get("agent_role") != "collation"]

        for agent_name in extraction_agents:
            edge = {
                "source": agent_name,
                "target": "collation_agent",
                "condition": None,
            }
            edges.append(edge)

    return edges


def create_autogen_agents(
    agent_configs: List[Dict[str, Any]],
    doc_id: Optional[str] = None,
) -> List[AssistantAgent]:
    """
    Create actual Autogen AssistantAgent instances.

    Args:
        agent_configs: List of agent configuration dictionaries
        doc_id: Document ID for RAG context

    Returns:
        List of AssistantAgent instances
    """
    agents = []

    # LLM configuration
    llm_config = {
        "model": "gpt-4",
        "temperature": 0.1,
        "timeout": 300,
    }

    for config in agent_configs:
        # Create AssistantAgent
        agent = AssistantAgent(
            name=config["name"],
            system_message=config["system_message"],
            llm_config=llm_config,
        )

        agents.append(agent)

    return agents


def add_edges_to_builder(
    builder: DiGraphBuilder,
    agents: List[AssistantAgent],
    dependencies: Dict[str, List[str]],
    tool_settings: Dict[str, Any],
) -> None:
    """
    Add edges to the DiGraphBuilder based on dependencies.

    Args:
        builder: DiGraphBuilder instance
        agents: List of AssistantAgent instances
        dependencies: Field dependencies
        tool_settings: Tool settings
    """
    # Create agent lookup by name
    agent_map = {agent.name: agent for agent in agents}

    # Add dependency edges
    for field_name, dep_fields in dependencies.items():
        # Find target agent for this field
        target_agent = None
        for agent in agents:
            if field_name in agent.name:
                target_agent = agent
                break

        if target_agent:
            for dep_field in dep_fields:
                # Find source agent for dependency
                source_agent = None
                for agent in agents:
                    if dep_field in agent.name:
                        source_agent = agent
                        break

                if source_agent:
                    builder.add_edge(source_agent, target_agent)

    # Add edges to challenger if enabled
    has_challenger = tool_settings.get("enable_challenge", False)
    challenger_agent = None
    collation_agent = None

    # Find special agents
    for agent in agents:
        if "challenger_agent" in agent.name:
            challenger_agent = agent
        elif "data_collation_agent" in agent.name:
            collation_agent = agent

    if has_challenger and challenger_agent:
        # All extraction agents → challenger
        for agent in agents:
            if agent != challenger_agent and agent != collation_agent:
                builder.add_edge(agent, challenger_agent)

        # Challenger → collation with condition
        if collation_agent:
            builder.add_edge(
                challenger_agent,
                collation_agent,
                condition=lambda msg: "approved" in msg.content.lower() or "validated" in msg.content.lower()
            )
    else:
        # Direct extraction agents → collation
        if collation_agent:
            for agent in agents:
                if agent != collation_agent:
                    builder.add_edge(agent, collation_agent)


def serialize_graph_flow(graph_flow: GraphFlow) -> Dict[str, Any]:
    """
    Serialize GraphFlow object for JSON storage.

    Args:
        graph_flow: GraphFlow instance

    Returns:
        Serialized representation
    """
    return {
        "type": "GraphFlow",
        "participants": [agent.name for agent in graph_flow.participants],
        "graph_info": "Graph structure serialized separately",
    }


def serialize_agent(agent: AssistantAgent) -> Dict[str, Any]:
    """
    Serialize AssistantAgent for JSON storage.

    Args:
        agent: AssistantAgent instance

    Returns:
        Serialized representation
    """
    return {
        "name": agent.name,
        "type": "AssistantAgent",
        "system_message": agent.system_message,
        "llm_config": getattr(agent, 'llm_config', {}),
    }


def serialize_graph(graph) -> Dict[str, Any]:
    """
    Serialize graph structure for JSON storage.

    Args:
        graph: Graph object from DiGraphBuilder

    Returns:
        Serialized representation
    """
    return {
        "type": "DiGraph",
        "info": "Graph structure from Autogen DiGraphBuilder",
    }


def verify_autogen_components(builder: DiGraphBuilder, graph_flow: GraphFlow) -> None:
    """
    Verify that we're using proper Autogen components.

    Args:
        builder: DiGraphBuilder instance
        graph_flow: GraphFlow instance
    """
    logger.info("Verifying Autogen components:")
    logger.info(f"DiGraphBuilder type: {type(builder)}")
    logger.info(f"GraphFlow type: {type(graph_flow)}")
    logger.info(f"Participants count: {len(graph_flow.participants)}")

    # Confirm we're using the right Autogen classes
    assert isinstance(builder, DiGraphBuilder), f"Expected DiGraphBuilder, got {type(builder)}"
    assert isinstance(graph_flow, GraphFlow), f"Expected GraphFlow, got {type(graph_flow)}"

    logger.info("✓ Successfully using Autogen DiGraphBuilder and GraphFlow for sequential team processing")


def execute_graph_flow(
    graph_flow: GraphFlow,
    task: str = "Extract all specified fields from the document accurately.",
) -> Dict[str, Any]:
    """
    Execute the GraphFlow and return results.

    Args:
        graph_flow: GraphFlow instance to execute
        task: Task description for the agents

    Returns:
        Execution results
    """
    results = {}
    final_output = None

    try:
        # Run the GraphFlow
        stream = graph_flow.run_stream(task=task)

        for event in stream:
            logger.info(f"Event: {event.type}, Agent: {event.source}")

            # Store results
            if hasattr(event, 'content') and event.content:
                results[event.source] = event.content

                # Check if this is the final collation result
                if event.source == 'data_collation_agent':
                    try:
                        final_output = json.loads(event.content)
                    except json.JSONDecodeError:
                        final_output = event.content

    except Exception as e:
        logger.error(f"Error executing GraphFlow: {str(e)}")
        raise

    return {
        "final_output": final_output,
        "all_results": results,
        "execution_status": "completed" if final_output else "incomplete",
    }


def generate_autogen_code(
    agents: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    doc_id: Optional[str],
    extraction_spec: Dict[str, Any],
) -> str:
    """
    Generate executable Autogen GraphFlow code using DiGraphBuilder.

    Args:
        agents: Agent configurations
        edges: Edge configurations
        doc_id: Document ID for RAG
        extraction_spec: Original extraction specification

    Returns:
        Executable Python code string following Autogen DiGraphBuilder format
    """
    code_lines = []

    # Imports following Autogen documentation
    code_lines.extend([
        "from autogen_agentchat.agents import AssistantAgent",
        "from autogen_agentchat.teams import DiGraphBuilder, GraphFlow",
        "import json",
        "",
    ])

    # LLM Configuration
    code_lines.extend([
        "# LLM Configuration - configure according to your setup",
        "llm_config = {",
        "    'model': 'gpt-4',",
        "    'temperature': 0.1,",
        "    'timeout': 300,",
        "}",
        "",
    ])

    # Document context
    if doc_id:
        code_lines.extend([
            f"# Document context for RAG",
            f'doc_id = "{doc_id}"',
            "",
        ])

    # Agent definitions
    code_lines.append("# Define agents")
    for agent in agents:
        agent_code = generate_agent_code(agent)
        code_lines.extend(agent_code)

    code_lines.append("")

    # Graph builder following Autogen pattern
    code_lines.extend([
        "# Build the graph using DiGraphBuilder",
        "builder = DiGraphBuilder()",
        "",
        "# Add nodes to the graph",
    ])

    # Add nodes using add_node method
    for agent in agents:
        code_lines.append(f"builder.add_node({agent['name']})")

    code_lines.extend([
        "",
        "# Add edges to define workflow",
    ])

    # Add edges using add_edge method
    for edge in edges:
        edge_code = generate_edge_code(edge)
        code_lines.append(edge_code)

    code_lines.extend([
        "",
        "# Build the graph",
        "graph = builder.build()",
        "",
        "# Create the GraphFlow",
        "flow = GraphFlow(participants=builder.get_participants(), graph=graph)",
        "",
        "# Define the extraction task",
        'task = """Extract all the specified fields from the document accurately. ',
        'Follow the workflow defined in the graph to ensure proper data extraction.',
        'Each agent should focus on their specific role and pass results to the next agent."""',
        "",
        "# Run the extraction flow",
        "stream = flow.run_stream(task=task)",
        "",
        "# Process the results",
        "results = {}",
        "final_output = None",
        "",
        "for event in stream:",
        "    print(f'Event: {event.type}')  # Event type",
        "    print(f'Agent: {event.source}')  # Source agent",
        "    print(f'Content: {event.content[:200]}...')  # First 200 chars",
        "    print('---')",
        "    ",
        "    # Store results",
        "    if hasattr(event, 'content') and event.content:",
        "        results[event.source] = event.content",
        "        ",
        "        # Check if this is the final collation result",
        "        if event.source == 'data_collation_agent':",
        "            try:",
        "                final_output = json.loads(event.content)",
        "            except json.JSONDecodeError:",
        "                final_output = event.content",
        "",
        "# Display final results",
        "print('\\n=== EXTRACTION COMPLETE ===')",
        "if final_output:",
        "    print('Final extracted data:')",
        "    if isinstance(final_output, dict):",
        "        print(json.dumps(final_output, indent=2))",
        "    else:",
        "        print(final_output)",
        "else:",
        "    print('No final output from collation agent')",
        "    print('All agent results:')",
        "    for agent_name, result in results.items():",
        "        print(f'{agent_name}: {result[:100]}...')",
    ])

    return "\n".join(code_lines)


def generate_agent_code(agent: Dict[str, Any]) -> List[str]:
    """Generate code lines for creating an agent."""
    name = agent["name"]
    agent_type = agent["agent_type"]
    system_message = agent["system_message"]

    # Escape quotes in system message
    escaped_message = system_message.replace('"""', '\\"\\"\\"')

    code_lines = [
        f'{name} = {agent_type}(',
        f'    name="{name}",',
        f'    system_message="""',
        f'{escaped_message}',
        f'    """,',
        f'    llm_config=llm_config',
        f')',
        "",
    ]

    return code_lines


def generate_edge_code(edge: Dict[str, Any]) -> str:
    """Generate code for creating an edge."""
    source = edge["source"]
    target = edge["target"]
    condition = edge.get("condition")

    if condition:
        return f"builder.add_edge({source}, {target}, condition={condition})"
    else:
        return f"builder.add_edge({source}, {target})"


def create_execution_plan(agents: List[Dict[str, Any]], dependencies: Dict[str, List[str]]) -> Dict[str, Any]:
    """Create execution plan information."""
    # Simple analysis of the execution flow
    extraction_agents = [a for a in agents if a.get("field_config", {}).get("agent_role") not in ["challenger", "collation"]]
    has_challenger = any(a.get("field_config", {}).get("agent_role") == "challenger" for a in agents)
    has_collation = any(a.get("field_config", {}).get("agent_role") == "collation" for a in agents)

    stages = ["Extraction"]
    if has_challenger:
        stages.append("Validation")
    if has_collation:
        stages.append("Collation")

    return {
        "stages": stages,
        "total_agents": len(agents),
        "extraction_agents": len(extraction_agents),
        "has_challenger": has_challenger,
        "has_collation": has_collation,
        "estimated_parallel_extraction": len(extraction_agents) > 1,
    }