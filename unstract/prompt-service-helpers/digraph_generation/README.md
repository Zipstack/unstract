# Digraph Generation Module - Prompt Service Helpers

This module generates directed graphs (digraphs) using Microsoft Autogen's DiGraphBuilder and GraphFlow for orchestrating sequential multi-agent data extraction workflows.

## Autogen Integration

This module directly uses Autogen components:
- **`autogen_agentchat.agents.AssistantAgent`** - For creating individual extraction agents
- **`autogen_agentchat.teams.DiGraphBuilder`** - For building directed graph structure
- **`autogen_agentchat.teams.GraphFlow`** - For sequential team execution

The implementation creates actual Autogen objects (not code generation) for immediate execution.

## Overview

The digraph generation module takes extraction specifications from the answer_prompt payload and creates executable Autogen GraphFlow code. It analyzes field dependencies, determines required agents, and generates a workflow that coordinates specialized extraction agents.

## Components

### 1. **digraph_task.py**
Main celery task that generates Autogen GraphFlow code.

**Key Features:**
- Parses extraction specifications from answer_prompt format
- Creates specialized agents based on field types and requirements
- Generates dependency graphs with proper execution order
- Outputs executable Python code using Autogen's DiGraphBuilder
- Supports parallel execution where possible

**Task Name:** `generate_extraction_digraph`

**Inputs:**
- `extraction_spec`: Extraction specification containing:
  - `outputs`: List of fields to extract (same as "prompts" in answer_prompt)
  - `tool_settings`: Configuration including `enable_challenge`
  - `dependencies`: Field dependencies (optional)
- `previous_stage_output`: Output from chunking/embedding stage containing:
  - `doc_id`: Document identifier for RAG access

**Outputs:**
- `autogen_code`: Executable Python code for Autogen GraphFlow
- `agents`: List of agent configurations
- `edges`: List of edge configurations
- `execution_plan`: Execution flow information
- `metadata`: Additional processing information

### 2. **spec_parser.py**
Parser for extraction specifications with predefined agent configurations.

**Predefined Agent Types:**
1. **Generic Data Extraction Agent**
   - Tools: RAG, Calculator
   - Purpose: General text field extraction

2. **Table Data Extraction Agent**
   - Tools: Calculator
   - Purpose: Tabular data extraction and processing

3. **Omniparse Data Extraction Agent**
   - Tools: Calculator
   - Purpose: Complex layouts, visual elements, non-standard formats

4. **Challenger Agent** (optional)
   - Tools: RAG, Calculator
   - Purpose: Validation and quality assurance

5. **Data Collation Agent** (always included)
   - Tools: String concatenation
   - Purpose: Combining and formatting final output

**Key Methods:**
- `parse(extraction_spec)`: Parse answer_prompt format to structured spec
- `create_agent_system_message()`: Generate system messages for agents
- `validate_spec()`: Validate the parsed specification

## Agent Selection Logic

The module automatically determines which agents to use based on field characteristics:

- **Table fields**: Uses `table_data_extraction_agent`
- **Visual/complex fields**: Uses `omniparse_data_extraction_agent`
- **Standard text fields**: Uses `generic_data_extraction_agent`
- **Challenger**: Added if `tool_settings.enable_challenge = true`
- **Collation**: Always added as the final agent

## Generated Autogen Code Structure

The output follows the official Autogen DiGraphBuilder pattern:

```python
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow

# 1. Define agents
agent_field1 = AssistantAgent("agent_field1", system_message="...")
agent_field2 = AssistantAgent("agent_field2", system_message="...")
challenger_agent = AssistantAgent("challenger_agent", system_message="...")
collation_agent = AssistantAgent("collation_agent", system_message="...")

# 2. Build the graph
builder = DiGraphBuilder()
builder.add_node(agent_field1).add_node(agent_field2).add_node(challenger_agent).add_node(collation_agent)

# 3. Add edges with conditions
builder.add_edge(agent_field1, challenger_agent)
builder.add_edge(agent_field2, challenger_agent)
builder.add_edge(challenger_agent, collation_agent, condition=lambda msg: "approved" in msg.content.lower())

# 4. Build and run
graph = builder.build()
flow = GraphFlow(participants=builder.get_participants(), graph=graph)
stream = flow.run_stream(task="Extract data from document")
```

## Usage Example

```python
from celery import Celery
from digraph_generation.digraph_task import generate_extraction_digraph

# Example extraction specification (answer_prompt format)
extraction_spec = {
    "outputs": [
        {
            "name": "company_name",
            "prompt": "Extract the company name from the document",
            "type": "text",
            "required": True
        },
        {
            "name": "financial_table",
            "prompt": "Extract the financial data table",
            "type": "table",
            "required": True
        }
    ],
    "tool_settings": {
        "enable_challenge": True
    },
    "dependencies": {
        "financial_table": ["company_name"]  # Table extraction depends on company name
    }
}

# Previous stage output from chunking/embedding
previous_output = {
    "doc_id": "abc123-def456",
    "chunk_count": 25,
    "embedding_count": 25
}

# Generate the digraph
result = generate_extraction_digraph.delay(
    extraction_spec=extraction_spec,
    previous_stage_output=previous_output
)

# Get the result
output = result.get()
print("Generated Autogen code:")
print(output["autogen_code"])

# Execute the generated code
exec(output["autogen_code"])
```

## Dependency Analysis

The module analyzes field dependencies in two ways:

1. **Explicit Dependencies**: Specified in the `dependencies` field
2. **Implicit Dependencies**: Detected from variable references in prompts (e.g., `{{other_field}}`)

Dependencies determine the execution order and edge conditions in the generated graph.

## Integration with Celery Chain

This task fits into the extraction pipeline as follows:

```
Text Extraction → Chunking & Embedding → Digraph Generation → Agent Execution
```

The `doc_id` from the chunking stage enables RAG functionality in the extraction agents.

## Agent System Messages

Each agent type has a specialized system message template:

- **Extraction agents**: Field-specific instructions with RAG/calculator guidance
- **Challenger agent**: Validation instructions with quality criteria
- **Collation agent**: JSON formatting and output structure instructions

## Graph Features

The generated graphs support:

- **Parallel Execution**: Independent fields can be extracted simultaneously
- **Conditional Edges**: Challenger approval gates and dependency conditions
- **Proper Termination**: Well-defined endpoints through collation agent
- **Error Handling**: Built into agent system messages and conditions

## Configuration

Environment variables for customization:
- `DIGRAPH_QUEUE`: Celery queue for digraph tasks (default: "processing_queue")
- `DIGRAPH_TIMEOUT`: Task timeout in seconds (default: 600)
- `ENABLE_CHALLENGER_DEFAULT`: Default challenger setting (default: false)

## Dependencies

Required packages:
- `celery>=5.3.0`
- `autogen-agentchat` (for Autogen GraphFlow)
- Standard Python libraries

## Future Enhancements

- Support for custom agent types
- Dynamic tool assignment based on document characteristics
- Advanced condition logic for complex workflows
- Integration with Unstract's tool registry for dynamic tool discovery
- Support for loops and iterative refinement workflows

## Validation

The module includes validation for:
- Field name uniqueness
- Dependency consistency (no circular dependencies)
- Agent configuration completeness
- Graph connectivity and termination conditions
