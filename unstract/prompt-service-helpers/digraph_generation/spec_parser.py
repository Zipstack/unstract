"""
Parser for extraction specifications from the answer_prompt payload.
Converts the prompt service payload format into Autogen DiGraphBuilder format.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExtractionSpecParser:
    """
    Parser for extraction specifications compatible with Autogen DiGraphBuilder.
    Uses predefined agent types with specific tools as per the specification.
    """

    # Predefined agent configurations with their tools
    AGENT_CONFIGS = {
        "generic_data_extraction_agent": {
            "tools": ["rag", "calculator"],
            "system_message_template": """You are a generic data extraction agent. Extract the field '{field_name}' from the document.

Field Description: {prompt}
Field Type: {field_type}
Required: {required}

Instructions:
1. Use RAG to search for relevant information in the document
2. Extract the specific information requested for this field
3. Use calculator for any numerical computations if needed
4. Ensure accuracy and completeness
5. If information is not found, clearly state it's unavailable

Tools available: RAG, Calculator"""
        },

        "table_data_extraction_agent": {
            "tools": ["calculator"],
            "system_message_template": """You are a table data extraction agent. Extract the field '{field_name}' from tabular data in the document.

Field Description: {prompt}
Field Type: {field_type}
Required: {required}

Instructions:
1. Identify and extract data from tables in the document
2. Preserve table structure and relationships
3. Use calculator for any numerical computations or aggregations
4. Ensure data accuracy and proper formatting
5. Handle missing or incomplete table data appropriately

Tools available: Calculator"""
        },

        "omniparse_data_extraction_agent": {
            "tools": ["calculator"],
            "system_message_template": """You are an omniparse data extraction agent specialized in complex document formats. Extract the field '{field_name}' from the document.

Field Description: {prompt}
Field Type: {field_type}
Required: {required}

Instructions:
1. Handle complex document layouts and formats
2. Extract from non-standard or visual elements
3. Use calculator for any numerical computations
4. Process complex data structures and relationships
5. Maintain accuracy across different document formats

Tools available: Calculator"""
        },

        "challenger_agent": {
            "tools": ["rag", "calculator"],
            "system_message_template": """You are a challenger agent responsible for validating extracted data quality.

Your role:
1. Review all extracted field values from other agents
2. Challenge incorrect, incomplete, or inconsistent extractions
3. Use RAG to verify information against the source document
4. Use calculator to verify numerical computations
5. Ensure required fields are properly extracted
6. Check for logical consistency between related fields

Validation criteria:
- Accuracy against source material
- Completeness for required fields
- Consistency across related fields
- Proper formatting and data types

If you find issues, specify what needs correction and why.
If extractions are accurate, approve them for final collation.

Tools available: RAG, Calculator"""
        },

        "data_collation_agent": {
            "tools": ["string_concatenation"],
            "system_message_template": """You are a data collation agent responsible for combining all validated field values into the final output.

Your role:
1. Collect all validated field values from extraction agents
2. Resolve any remaining conflicts between extractions
3. Format the final output as a structured JSON object
4. Ensure all required fields are included
5. Apply final formatting and string operations

Output format:
{{
{field_json_structure}
}}

Instructions:
- Use the most recent validated values for each field
- Apply string concatenation and formatting as needed
- Ensure proper JSON structure
- Include null for missing fields

Tools available: String concatenation"""
        }
    }

    def parse(self, extraction_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse the extraction specification from answer_prompt payload format.

        Args:
            extraction_spec: Raw extraction specification containing:
                - outputs: List of field specifications (same as "prompts" in answer_prompt)
                - tool_settings: Tool configuration including enable_challenge
                - Other metadata from answer_prompt payload

        Returns:
            Parsed specification ready for Autogen DiGraphBuilder
        """
        try:
            # Extract components from answer_prompt payload structure
            outputs = extraction_spec.get("outputs", [])  # Same as "prompts" in answer_prompt
            tool_settings = extraction_spec.get("tool_settings", {})

            # Parse fields from outputs
            fields = self._parse_fields(outputs)

            # Determine which agents are needed based on field types
            required_agents = self._determine_required_agents(fields, tool_settings)

            # Parse dependencies
            dependencies = self._parse_dependencies(
                extraction_spec.get("dependencies", {}),
                fields
            )

            # Extract metadata
            metadata = self._extract_metadata(extraction_spec)

            parsed_spec = {
                "fields": fields,
                "required_agents": required_agents,
                "tool_settings": tool_settings,
                "dependencies": dependencies,
                "metadata": metadata,
            }

            logger.info(f"Parsed extraction spec: {len(fields)} fields, {len(required_agents)} agents")
            return parsed_spec

        except Exception as e:
            logger.error(f"Error parsing extraction spec: {str(e)}")
            raise ValueError(f"Invalid extraction specification: {str(e)}")

    def _parse_fields(self, outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Parse field specifications from outputs (prompts from answer_prompt).

        Args:
            outputs: List of output/prompt specifications

        Returns:
            List of parsed field specifications
        """
        fields = []

        for output in outputs:
            # Extract field information following answer_prompt structure
            field = {
                "name": output.get("name", ""),
                "prompt": output.get("prompt", ""),
                "type": output.get("type", "text"),
                "required": output.get("required", False),
                "chunk_size": output.get("chunk_size", 1000),
                "chunk_overlap": output.get("chunk_overlap", 200),
            }

            # Determine agent type based on field characteristics
            field["agent_type"] = self._determine_field_agent_type(field)

            # Validate required fields
            if not field["name"] or not field["prompt"]:
                logger.warning(f"Skipping invalid field: {field}")
                continue

            fields.append(field)

        return fields

    def _determine_field_agent_type(self, field: Dict[str, Any]) -> str:
        """
        Determine which agent type should handle this field.

        Args:
            field: Field specification

        Returns:
            Agent type name
        """
        field_type = field.get("type", "text").lower()
        prompt = field.get("prompt", "").lower()

        # Check for table extraction
        if field_type == "table" or "table" in prompt:
            return "table_data_extraction_agent"

        # Check for complex/omniparse extraction
        if field_type in ["image", "chart", "diagram", "complex"] or any(
            keyword in prompt for keyword in ["image", "chart", "diagram", "visual", "complex", "layout"]
        ):
            return "omniparse_data_extraction_agent"

        # Default to generic extraction
        return "generic_data_extraction_agent"

    def _determine_required_agents(
        self,
        fields: List[Dict[str, Any]],
        tool_settings: Dict[str, Any]
    ) -> List[str]:
        """
        Determine which agents are required based on fields and settings.

        Args:
            fields: List of field specifications
            tool_settings: Tool settings from payload

        Returns:
            List of required agent type names
        """
        required_agents = set()

        # Add agents based on field requirements
        for field in fields:
            required_agents.add(field["agent_type"])

        # Add challenger agent if enabled
        if tool_settings.get("enable_challenge", False):
            required_agents.add("challenger_agent")

        # Always add collation agent
        required_agents.add("data_collation_agent")

        return list(required_agents)

    def _parse_dependencies(
        self,
        explicit_dependencies: Dict[str, Any],
        fields: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """
        Parse field dependencies including implicit dependencies from variable references.

        Args:
            explicit_dependencies: Explicitly defined dependencies
            fields: List of field specifications

        Returns:
            Complete dependency mapping
        """
        dependencies = {}

        # Start with explicit dependencies
        for field_name, deps in explicit_dependencies.items():
            if isinstance(deps, list):
                dependencies[field_name] = [dep for dep in deps if isinstance(dep, str)]
            elif isinstance(deps, str):
                dependencies[field_name] = [deps]

        # Analyze implicit dependencies from variable references in prompts
        for field in fields:
            field_name = field.get("name", "")
            prompt_text = field.get("prompt", "")

            # Find variable references like {{other_field}}
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

    def _extract_metadata(self, extraction_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from the extraction specification.

        Args:
            extraction_spec: Raw extraction specification

        Returns:
            Extracted metadata
        """
        metadata = {}

        # Common metadata fields from answer_prompt payload
        metadata_fields = [
            "tool_id", "run_id", "execution_id", "file_hash", "file_path",
            "file_name", "log_events_id", "execution_source", "user_data"
        ]

        for field in metadata_fields:
            if field in extraction_spec:
                metadata[field] = extraction_spec[field]

        return metadata

    def get_agent_config(self, agent_type: str) -> Dict[str, Any]:
        """
        Get the configuration for a specific agent type.

        Args:
            agent_type: Type of agent

        Returns:
            Agent configuration including tools and system message template
        """
        return self.AGENT_CONFIGS.get(agent_type, {})

    def create_agent_system_message(
        self,
        agent_type: str,
        field: Optional[Dict[str, Any]] = None,
        all_fields: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Create system message for an agent.

        Args:
            agent_type: Type of agent
            field: Field specification for extraction agents
            all_fields: All fields for challenger/collation agents

        Returns:
            Formatted system message
        """
        config = self.get_agent_config(agent_type)
        template = config.get("system_message_template", "")

        if field:
            # For extraction agents
            return template.format(
                field_name=field.get("name", ""),
                prompt=field.get("prompt", ""),
                field_type=field.get("type", "text"),
                required=field.get("required", False)
            )
        elif all_fields and agent_type == "data_collation_agent":
            # For collation agent, create JSON structure
            field_json_structure = ',\n'.join([
                f'  "{field.get("name", "")}": "extracted_value"'
                for field in all_fields
            ])
            return template.format(field_json_structure=field_json_structure)

        return template

    def validate_spec(self, parsed_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate the parsed extraction specification.

        Args:
            parsed_spec: Parsed extraction specification

        Returns:
            Validation results
        """
        issues = []
        warnings = []

        fields = parsed_spec.get("fields", [])
        dependencies = parsed_spec.get("dependencies", {})

        # Check if we have fields
        if not fields:
            issues.append("No fields specified for extraction")

        # Validate field names are unique
        field_names = [field.get("name") for field in fields]
        if len(field_names) != len(set(field_names)):
            issues.append("Duplicate field names found")

        # Validate dependencies reference existing fields
        for field_name, deps in dependencies.items():
            if field_name not in field_names:
                warnings.append(f"Dependency for unknown field: {field_name}")

            for dep in deps:
                if dep not in field_names:
                    warnings.append(f"Field '{field_name}' depends on unknown field: {dep}")

        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "field_count": len(fields),
            "required_agent_count": len(parsed_spec.get("required_agents", [])),
        }