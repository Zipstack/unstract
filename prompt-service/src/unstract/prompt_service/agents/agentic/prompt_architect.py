"""PromptArchitectAgent: Generates initial extraction prompts from JSON Schema.

This agent creates optimized extraction prompts that guide LLMs to extract
structured data matching the provided JSON Schema.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)


class PromptArchitectAgent:
    """Agent that generates initial extraction prompts from JSON Schema.

    This agent:
    1. Analyzes the JSON Schema structure
    2. Creates clear, detailed extraction instructions
    3. Includes field descriptions and examples
    4. Adds formatting requirements
    5. Includes source reference instructions
    6. Optimizes for LLM understanding
    """

    SYSTEM_PROMPT = """You are an expert prompt engineer specializing in data extraction. Your task is to create highly effective prompts that guide LLMs to extract structured data from documents.

Your responsibilities:
1. **Understand the Schema**: Analyze the JSON Schema to understand what data to extract
2. **Create Clear Instructions**: Write explicit, unambiguous extraction instructions
3. **Include Field Guidance**: For each field, explain:
   - What to extract
   - Where to find it
   - How to format it
   - Examples of expected values
4. **Handle Edge Cases**: Provide guidance for:
   - Missing fields (extract null or empty string)
   - Multiple values (how to handle)
   - Ambiguous values (which to choose)
   - Format variations (dates, numbers, etc.)
5. **Optimize for Accuracy**: Use techniques that improve extraction quality:
   - Chain-of-thought reasoning
   - Step-by-step instructions
   - Output format examples
   - Validation hints
6. **Include Source References**: Instruct LLM to note where data was found (for highlight metadata)

Prompt Structure (use this template):
```
# Document Data Extraction Task

## Objective
Extract structured data from the provided document according to the schema below.

## Schema
{json_schema}

## Extraction Instructions

### General Guidelines
1. Read the document carefully
2. Extract ALL fields from the schema
3. If a field is not found, use null
4. Match the exact data types specified
5. Follow the format requirements

### Field-by-Field Instructions
{field_instructions}

### Output Format
Return the extracted data as a JSON object matching the schema exactly.

Example output structure:
{example_output}

### Important Rules
- Extract COMPLETE values (don't truncate)
- Preserve original formatting for numbers and dates
- For arrays, extract ALL instances
- Double-check required fields

## Document Text
{document_text}

## Your Response
Please extract the data as JSON:
```

Best Practices:
- Be extremely clear and specific
- Use examples liberally
- Anticipate common extraction errors
- Guide the LLM step-by-step
- Make the expected output format obvious

Return ONLY the extraction prompt text, no other commentary."""

    def __init__(self, model_client: ChatCompletionClient):
        """Initialize the PromptArchitectAgent.

        Args:
            model_client: AutoGen ChatCompletionClient (e.g., UnstractAutogenBridge)
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="PromptArchitectAgent",
            model_client=model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("Initialized PromptArchitectAgent")

    async def generate_prompt(
        self,
        json_schema: Dict[str, Any],
        example_documents: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate initial extraction prompt from JSON Schema.

        Args:
            json_schema: Valid JSON Schema (from FinalizerAgent)
            example_documents: Optional list of example docs with extracted data

        Returns:
            Dict with generated prompt:
            {
                "prompt_text": "...",  # The extraction prompt
                "metadata": {...},  # Prompt generation metadata
                "field_count": int,  # Number of fields
                "includes_examples": bool  # Whether examples are included
            }
        """
        try:
            # Analyze schema
            schema_analysis = self._analyze_schema(json_schema)

            # Format schema and examples for agent
            schema_description = self._format_schema(json_schema, schema_analysis)
            examples_text = self._format_examples(example_documents) if example_documents else "No examples provided"

            # Create prompt for the agent
            user_message = f"""Create an optimized extraction prompt for this schema:

{schema_description}

{examples_text}

The prompt should:
1. Clearly explain what data to extract
2. Provide field-by-field guidance
3. Include format requirements and examples
4. Handle edge cases and missing values
5. Be optimized for high accuracy extraction

Return the complete extraction prompt."""

            # Send message to agent
            response = await self.agent.on_messages(
                [TextMessage(content=user_message, source="user")],
                cancellation_token=None,
            )

            # Extract response content
            if hasattr(response, "chat_message") and hasattr(
                response.chat_message, "content"
            ):
                prompt_text = response.chat_message.content
            else:
                prompt_text = str(response)

            # Clean up prompt text
            prompt_text = self._clean_prompt_text(prompt_text)

            logger.info(
                f"Generated extraction prompt: {len(prompt_text)} chars, "
                f"{schema_analysis['total_fields']} fields"
            )

            return {
                "prompt_text": prompt_text,
                "metadata": {
                    "schema_analysis": schema_analysis,
                    "has_examples": bool(example_documents),
                    "example_count": len(example_documents) if example_documents else 0,
                },
                "field_count": schema_analysis["total_fields"],
                "includes_examples": bool(example_documents),
            }

        except Exception as e:
            logger.error(f"Prompt generation failed: {e}")
            raise

    def _analyze_schema(self, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze JSON Schema structure.

        Args:
            json_schema: JSON Schema to analyze

        Returns:
            Dict with schema analysis
        """
        analysis = {
            "total_fields": 0,
            "required_fields": [],
            "optional_fields": [],
            "nested_objects": [],
            "arrays": [],
            "field_types": {},
            "has_descriptions": 0,
            "has_examples": 0,
        }

        def analyze_properties(properties: Dict, prefix: str = ""):
            """Recursively analyze properties."""
            for field_name, field_schema in properties.items():
                full_path = f"{prefix}.{field_name}" if prefix else field_name
                analysis["total_fields"] += 1

                field_type = field_schema.get("type", "string")
                analysis["field_types"][full_path] = field_type

                if "description" in field_schema:
                    analysis["has_descriptions"] += 1
                if "examples" in field_schema:
                    analysis["has_examples"] += 1

                if field_type == "object":
                    analysis["nested_objects"].append(full_path)
                    nested_props = field_schema.get("properties", {})
                    analyze_properties(nested_props, full_path)

                elif field_type == "array":
                    analysis["arrays"].append(full_path)
                    items = field_schema.get("items", {})
                    if items.get("type") == "object":
                        item_props = items.get("properties", {})
                        analyze_properties(item_props, f"{full_path}[]")

        if json_schema.get("type") == "object":
            properties = json_schema.get("properties", {})
            required = json_schema.get("required", [])

            analysis["required_fields"] = required
            analysis["optional_fields"] = [
                f for f in properties.keys() if f not in required
            ]

            analyze_properties(properties)

        return analysis

    def _format_schema(
        self, json_schema: Dict[str, Any], analysis: Dict[str, Any]
    ) -> str:
        """Format JSON Schema for agent input.

        Args:
            json_schema: JSON Schema object
            analysis: Schema analysis from _analyze_schema

        Returns:
            Formatted schema description
        """
        lines = []

        lines.append("## JSON Schema")
        lines.append(f"```json\n{json.dumps(json_schema, indent=2)}\n```")
        lines.append("")

        lines.append("## Schema Summary")
        lines.append(f"- Total Fields: {analysis['total_fields']}")
        lines.append(f"- Required Fields: {len(analysis['required_fields'])}")
        lines.append(f"- Optional Fields: {len(analysis['optional_fields'])}")
        lines.append(f"- Nested Objects: {len(analysis['nested_objects'])}")
        lines.append(f"- Arrays: {len(analysis['arrays'])}")
        lines.append("")

        if analysis['required_fields']:
            lines.append("## Required Fields")
            for field in analysis['required_fields']:
                lines.append(f"- {field}")
            lines.append("")

        return "\n".join(lines)

    def _format_examples(self, example_documents: List[Dict[str, Any]]) -> str:
        """Format example documents for agent input.

        Args:
            example_documents: List of example docs with extracted data

        Returns:
            Formatted examples text
        """
        if not example_documents:
            return ""

        lines = []
        lines.append("## Example Documents and Expected Outputs")
        lines.append("")

        for i, example in enumerate(example_documents[:3], 1):  # Limit to 3 examples
            doc_text = example.get("document_text", "")
            extracted_data = example.get("extracted_data", {})

            lines.append(f"### Example {i}")
            lines.append("Document:")
            lines.append(f"```\n{doc_text[:500]}...\n```")  # Truncate long docs
            lines.append("")
            lines.append("Expected Output:")
            lines.append(f"```json\n{json.dumps(extracted_data, indent=2)}\n```")
            lines.append("")

        return "\n".join(lines)

    def _clean_prompt_text(self, prompt_text: str) -> str:
        """Clean and format prompt text.

        Args:
            prompt_text: Raw prompt from agent

        Returns:
            Cleaned prompt text
        """
        # Remove markdown code blocks if agent wrapped it
        cleaned = prompt_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```)
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        return cleaned.strip()

    def create_field_instructions(self, json_schema: Dict[str, Any]) -> str:
        """Create detailed field-by-field extraction instructions.

        Args:
            json_schema: JSON Schema

        Returns:
            Formatted field instructions
        """
        lines = []
        properties = json_schema.get("properties", {})
        required = json_schema.get("required", [])

        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type", "string")
            description = field_schema.get("description", "")
            examples = field_schema.get("examples", [])
            is_required = field_name in required

            lines.append(f"### {field_name}")
            lines.append(f"**Type:** {field_type}")
            lines.append(f"**Required:** {'Yes' if is_required else 'No'}")
            if description:
                lines.append(f"**Description:** {description}")
            if examples:
                # Ensure examples is a list before slicing
                if isinstance(examples, list):
                    lines.append(f"**Examples:** {', '.join(map(str, examples[:3]))}")
                else:
                    lines.append(f"**Examples:** {str(examples)}")

            # Add type-specific guidance
            if field_type == "string":
                lines.append("- Extract the complete text value")
                lines.append("- Preserve original formatting")
            elif field_type in ["number", "integer"]:
                lines.append("- Extract as a numeric value")
                lines.append("- Remove currency symbols and commas")
            elif field_type == "array":
                lines.append("- Extract ALL instances as an array")
                lines.append("- Return empty array if none found")

            lines.append("")

        return "\n".join(lines)
