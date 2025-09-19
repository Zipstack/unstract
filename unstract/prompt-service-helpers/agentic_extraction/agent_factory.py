"""
Agent factory for creating Autogen agents with RAG tool integration.
This factory creates specialized extraction agents that use RAG for document retrieval,
following the answer_prompt format from the current prompt service.
"""

import logging
from typing import Any, Dict, List, Optional

from autogen_agentchat.agents import AssistantAgent

from .tools.rag_tool import RAGTool, RetrievalStrategy

logger = logging.getLogger(__name__)


class AgentFactory:
    """
    Factory for creating Autogen agents with RAG tool integration.
    Focuses on creating agents that can use RAG for document-based extraction,
    using answer_prompt format field configurations.
    """

    def __init__(self, doc_id: str, platform_key: Optional[str] = None):
        """
        Initialize agent factory for creating field-specific RAG tools.

        Args:
            doc_id: Document identifier for retrieval
            platform_key: Platform API key
        """
        self.doc_id = doc_id
        self.platform_key = platform_key

    def create_agent(
        self,
        agent_config: Dict[str, Any],
        field_config: Optional[Dict[str, Any]] = None,
    ) -> AssistantAgent:
        """
        Create an Autogen agent based on configuration with field-specific RAG.

        Args:
            agent_config: Agent configuration from digraph generation
            field_config: Field configuration from answer_prompt format (optional)

        Returns:
            AssistantAgent instance with field-specific RAG tool integration
        """
        agent_name = agent_config.get("name", "extraction_agent")
        agent_type = agent_config.get("agent_type", "AssistantAgent")
        system_message = agent_config.get("system_message", "")
        tools = agent_config.get("tools", [])

        # Create field-specific RAG tool if needed
        rag_tool = None
        if "rag" in tools and field_config:
            rag_tool = self._create_field_specific_rag_tool(field_config)
        elif "rag" in tools:
            # Default RAG tool
            rag_tool = RAGTool(
                doc_id=self.doc_id,
                platform_key=self.platform_key,
                retrieval_strategy=RetrievalStrategy.SIMPLE,
            )

        # Enhance system message with RAG tool instructions
        enhanced_system_message = self._enhance_system_message_with_rag(
            system_message, agent_name, tools, field_config
        )

        # Create LLM config with field-specific settings
        llm_config = self._create_llm_config(field_config)

        # Add RAG tool to function calling if agent uses RAG
        if rag_tool:
            llm_config["functions"] = [rag_tool.to_autogen_function()]

        # Create the agent
        agent = AssistantAgent(
            name=agent_name,
            system_message=enhanced_system_message,
            llm_config=llm_config,
        )

        logger.info(f"Created agent: {agent_name} with tools: {tools} for field: {field_config.get('name', 'unknown') if field_config else 'none'}")
        return agent

    def _create_field_specific_rag_tool(self, field_config: Dict[str, Any]) -> RAGTool:
        """
        Create a RAG tool with field-specific configuration from answer_prompt format.

        Args:
            field_config: Field configuration from answer_prompt

        Returns:
            Configured RAG tool instance
        """
        # Extract field-specific parameters
        chunk_size = field_config.get("chunk-size", None)
        chunk_overlap = field_config.get("chunk-overlap", None)
        top_k = field_config.get("similarity-top-k", 5)
        strategy = field_config.get("retrieval-strategy", "simple")
        embedding_id = field_config.get("embedding", None)
        vector_db_id = field_config.get("vector-db", None)

        # Map strategy string to enum
        try:
            retrieval_strategy = RetrievalStrategy(strategy)
        except ValueError:
            logger.warning(f"Unknown retrieval strategy: {strategy}, using simple")
            retrieval_strategy = RetrievalStrategy.SIMPLE

        # Create RAG tool with field-specific configuration
        return RAGTool(
            doc_id=self.doc_id,
            platform_key=self.platform_key,
            embedding_instance_id=embedding_id,
            vector_db_instance_id=vector_db_id,
            top_k=top_k,
            retrieval_strategy=retrieval_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def _create_llm_config(self, field_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create LLM configuration with field-specific settings.

        Args:
            field_config: Field configuration from answer_prompt

        Returns:
            LLM configuration dictionary
        """
        llm_config = {
            "model": "gpt-4",
            "temperature": 0.1,
            "timeout": 300,
        }

        if field_config:
            # Use field-specific LLM if provided
            llm_instance_id = field_config.get("llm")
            if llm_instance_id:
                llm_config["llm_instance_id"] = llm_instance_id

        return llm_config

    def _enhance_system_message_with_rag(
        self,
        base_system_message: str,
        agent_name: str,
        tools: List[str],
        field_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Enhance system message with field-specific RAG tool instructions.

        Args:
            base_system_message: Original system message
            agent_name: Name of the agent
            tools: List of tools available to the agent
            field_config: Field configuration from answer_prompt

        Returns:
            Enhanced system message with RAG instructions
        """
        if "rag" not in tools:
            return base_system_message

        # Get field-specific details
        field_name = field_config.get("name", "unknown") if field_config else "unknown"
        field_type = field_config.get("type", "text") if field_config else "text"
        retrieval_strategy = field_config.get("retrieval-strategy", "simple") if field_config else "simple"
        chunk_size = field_config.get("chunk-size", "default") if field_config else "default"

        rag_instructions = f"""

RAG Tool Instructions:
You have access to a RAG (Retrieval-Augmented Generation) tool for document retrieval.
Document ID: {self.doc_id}
Field: {field_name} (Type: {field_type})
Retrieval Strategy: {retrieval_strategy}
Chunk Size: {chunk_size}

Use the RAG tool to:
1. Search for relevant information: rag_search(query="your search query")
2. Get context for your specific field: Use queries related to {field_name}
3. Verify your extractions: Search for confirming or contradicting information

RAG Tool Usage for {field_type} field:
- Always search for relevant content before making extractions
- Use specific queries related to {field_name}
- Include multiple search queries if needed to gather comprehensive information
- The retrieval strategy is optimized for {retrieval_strategy} search patterns

Example RAG usage for {field_name}:
- Primary search: rag_search(query="{field_name}")
- Context search: rag_search(query="{field_name} context information")
- Verification search: rag_search(query="confirm {field_name} details")

For {field_type} fields:
- Focus on extracting precise {field_type} data
- Use the configured retrieval strategy ({retrieval_strategy}) for optimal results
- Chunk size is set to {chunk_size} for this field

Remember: The RAG tool retrieves actual content from the document using answer_prompt compatible retrieval.
"""

        return base_system_message + rag_instructions

    def create_generic_extraction_agent(
        self,
        field_config: Dict[str, Any],
        required: bool = False,
    ) -> AssistantAgent:
        """
        Create a generic data extraction agent with field-specific RAG from answer_prompt format.

        Args:
            field_config: Field configuration from answer_prompt outputs
            required: Whether the field is required

        Returns:
            AssistantAgent for generic extraction
        """
        field_name = field_config.get("name", "unknown_field")
        field_prompt = field_config.get("prompt", "")
        field_type = field_config.get("type", "text")

        system_message = f"""You are a generic data extraction agent. Your task is to extract the field '{field_name}' from the document.

Field: {field_name}
Type: {field_type}
Prompt: {field_prompt}
Required: {required}
Document ID: {self.doc_id}

Instructions:
1. Use the RAG tool to search for relevant information about this field
2. Search with multiple queries if needed to gather comprehensive information
3. Extract the specific information requested for this field
4. Ensure accuracy and completeness based on the field type ({field_type})
5. If information is not found, clearly state it's unavailable

Extraction Process:
1. Start by searching for content related to the field: rag_search(query="{field_name}")
2. Use field-specific queries: rag_search(query="{field_prompt}")
3. Analyze the retrieved information
4. Extract the specific value requested
5. Verify your extraction with additional searches if uncertain
6. Provide the final extracted value

Output format: Return only the extracted value for the field, formatted according to type {field_type}."""

        agent_config = {
            "name": f"generic_extraction_agent_{field_name}",
            "agent_type": "AssistantAgent",
            "system_message": system_message,
            "tools": ["rag"],
        }

        return self.create_agent(agent_config, field_config)

    def create_table_extraction_agent(
        self,
        field_config: Dict[str, Any],
        required: bool = False,
    ) -> AssistantAgent:
        """
        Create a table data extraction agent with field-specific RAG from answer_prompt format.

        Args:
            field_config: Field configuration from answer_prompt outputs
            required: Whether the field is required

        Returns:
            AssistantAgent for table extraction
        """
        field_name = field_config.get("name", "unknown_table")
        field_prompt = field_config.get("prompt", "")
        table_settings = field_config.get("table_settings", {})

        system_message = f"""You are a table data extraction agent. Your task is to extract the field '{field_name}' which contains tabular data.

Field: {field_name}
Type: table
Prompt: {field_prompt}
Required: {required}
Table Settings: {table_settings}
Document ID: {self.doc_id}

Instructions:
1. Use the RAG tool to search for tables and tabular data in the document
2. Look for structured data, tables, lists, or formatted information
3. Search with queries like "table", "data", the field name, and related terms
4. Extract and preserve the table structure
5. Format the output according to table_settings if provided

Table Extraction Process:
1. Search for table-related content: rag_search(query="table {field_name}")
2. Search for structured data: rag_search(query="data list {field_name}")
3. Look for specific table elements mentioned in the field description
4. Use the field prompt for targeted searches: rag_search(query="{field_prompt}")
5. Combine and structure the found tabular information
6. Present in a clear, structured format

Output format: Return the table data in a structured format (JSON, CSV-like, or clear text structure) based on table_settings."""

        agent_config = {
            "name": f"table_extraction_agent_{field_name}",
            "agent_type": "AssistantAgent",
            "system_message": system_message,
            "tools": ["rag"],
        }

        return self.create_agent(agent_config, field_config)

    def create_omniparse_extraction_agent(
        self,
        field_config: Dict[str, Any],
        required: bool = False,
    ) -> AssistantAgent:
        """
        Create an omniparse data extraction agent with field-specific RAG from answer_prompt format.

        Args:
            field_config: Field configuration from answer_prompt outputs
            required: Whether the field is required

        Returns:
            AssistantAgent for complex extraction
        """
        field_name = field_config.get("name", "unknown_field")
        field_prompt = field_config.get("prompt", "")
        field_type = field_config.get("type", "text")

        system_message = f"""You are an omniparse data extraction agent specialized in complex document formats. Your task is to extract the field '{field_name}'.

Field: {field_name}
Type: {field_type}
Prompt: {field_prompt}
Required: {required}
Document ID: {self.doc_id}

Instructions:
1. Use the RAG tool to search for complex or visual content related to this field
2. Handle non-standard formats, visual elements, or complex layouts
3. Search with multiple approaches to find the information
4. Look for information that might be in charts, diagrams, or complex structures
5. Use comprehensive search strategies with the configured retrieval method

Complex Extraction Process:
1. Broad search: rag_search(query="{field_name}")
2. Prompt-based search: rag_search(query="{field_prompt}")
3. Visual/format search: rag_search(query="chart diagram figure {field_name}")
4. Context search: rag_search(query="visual image content {field_name}")
5. Structure search: rag_search(query="layout format {field_name}")
6. Combine information from multiple sources
7. Extract and interpret the complex data

Output format: Return the extracted information with clear indication of its source and format, formatted as {field_type}."""

        agent_config = {
            "name": f"omniparse_extraction_agent_{field_name}",
            "agent_type": "AssistantAgent",
            "system_message": system_message,
            "tools": ["rag"],
        }

        return self.create_agent(agent_config, field_config)

    def create_challenger_agent(self, fields: List[Dict[str, Any]]) -> AssistantAgent:
        """
        Create a challenger agent for validation with RAG using answer_prompt field configurations.

        Args:
            fields: List of field configurations from answer_prompt outputs

        Returns:
            AssistantAgent for validation
        """
        field_names = [f.get("name", "") for f in fields]
        field_types = {f.get("name", ""): f.get("type", "text") for f in fields}

        system_message = f"""You are a challenger agent responsible for validating extracted data quality using RAG.

Fields to validate: {', '.join(field_names)}
Field types: {field_types}
Document ID: {self.doc_id}

Your role:
1. Review all extracted field values from other agents
2. Use RAG to verify each extraction against the source document
3. Challenge incorrect, incomplete, or inconsistent extractions
4. Verify that required fields are properly extracted
5. Check for logical consistency between related fields
6. Validate data types match expected field types

Validation process:
1. For each extracted field, use RAG to search for confirming evidence
2. Use queries like: rag_search(query="[field_name] [extracted_value]")
3. Look for contradictory information
4. Verify completeness and accuracy according to field type
5. Check format consistency (e.g., dates, numbers, emails)
6. Provide specific feedback for corrections

If you find issues, clearly state what needs to be corrected and why.
If extractions are accurate and properly formatted, approve them for final collation.

Output format: For each field, state "APPROVED: [field_name]" or "REJECTED: [field_name] - [specific reason with evidence]" """

        agent_config = {
            "name": "challenger_agent",
            "agent_type": "AssistantAgent",
            "system_message": system_message,
            "tools": ["rag"],
        }

        return self.create_agent(agent_config)

    def create_collation_agent(self, fields: List[Dict[str, Any]]) -> AssistantAgent:
        """
        Create a data collation agent using answer_prompt field configurations.

        Args:
            fields: List of field configurations from answer_prompt outputs

        Returns:
            AssistantAgent for collation
        """
        field_names = [f.get("name", "") for f in fields]
        field_types = {f.get("name", ""): f.get("type", "text") for f in fields}
        field_json_structure = ',\n'.join([
            f'  "{name}": "extracted_value"  // Type: {field_types.get(name, "text")}'
            for name in field_names
        ])

        system_message = f"""You are a data collation agent responsible for combining all validated field values into the final output.

Fields to collate: {', '.join(field_names)}
Field types: {field_types}

Your role:
1. Collect all validated field values from extraction agents
2. Resolve any remaining conflicts between extractions
3. Format the final output as a structured JSON object
4. Ensure all required fields are included
5. Apply any final formatting or transformations based on field types
6. Validate data types before final output

Output format:
{{
{field_json_structure}
}}

Instructions:
- Use the most recent validated values for each field
- If multiple values exist for a field, use your judgment to select the best one
- Ensure the output JSON is properly formatted
- Include null values for fields that couldn't be extracted
- Respect field types when formatting values:
  * text: string values
  * number: numeric values
  * date: ISO date format
  * email: valid email format
  * boolean: true/false
  * json: valid JSON object
  * table: structured table format
- Do not use RAG - only work with the extracted values provided by other agents

Note: You do not have access to RAG tool - focus on organizing and formatting the extracted data."""

        agent_config = {
            "name": "data_collation_agent",
            "agent_type": "AssistantAgent",
            "system_message": system_message,
            "tools": [],  # No RAG for collation agent
        }

        return self.create_agent(agent_config)