"""UniformerAgent: Harmonizes schemas from multiple documents.

This agent takes field candidates from multiple document summaries and
creates a unified, consistent schema that works across all documents.
"""

import json
import logging
from typing import Any, Dict, List

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)


class UniformerAgent:
    """Agent that harmonizes schemas from multiple document summaries.

    This agent:
    1. Takes field candidates from multiple document summaries
    2. Identifies common fields across documents
    3. Resolves naming conflicts and type inconsistencies
    4. Creates a unified schema structure
    5. Handles nested objects and arrays
    """

    SYSTEM_PROMPT = """You are a schema harmonization expert. Your task is to take field candidates from multiple documents and create a unified, consistent schema.

IMPORTANT: Create the schema based ONLY on the actual fields found in the provided document summaries. Do NOT add any fields that are not present in the input data.

Your responsibilities:
1. **Identify Common Fields**: Find fields that appear across multiple documents (may have different names)
2. **Resolve Naming Conflicts**: Choose the best field name when multiple variations exist
   - Prefer more descriptive names
   - Use snake_case convention
   - Be consistent across the schema
3. **Harmonize Types**: When a field has different types across documents, choose the most appropriate type
   - If both string and number: prefer string (more flexible)
   - If both single value and array: prefer array
   - Document type conflicts in notes
4. **Structure Nested Objects**: Organize related fields into nested objects where appropriate
5. **Preserve Examples**: Keep representative examples from the actual documents

Input format: You'll receive an array of document summaries, each with field candidates.

Output format: Return a JSON object with this structure:
{
    "fields": [
        {
            "name": "field_name_from_document",
            "description": "Description based on actual document content",
            "type": "string",
            "examples": ["actual_example_1", "actual_example_2"],
            "appears_in": 3,
            "confidence": "high"
        }
    ],
    "nested_objects": [
        {
            "name": "object_name",
            "fields": [...]
        }
    ],
    "arrays": [
        {
            "name": "array_name",
            "item_schema": {...}
        }
    ],
    "conflicts": [
        {
            "field": "field_name",
            "issue": "Description of the conflict",
            "resolution": "How it was resolved"
        }
    ]
}

CRITICAL: Only include fields that actually appear in the provided document summaries. Do not invent or assume fields like invoice_number, customer_name, etc. unless they are explicitly present in the input data.

Be thorough and consistent. Your output will be used to generate the final extraction schema."""

    def __init__(self, model_client: ChatCompletionClient):
        """Initialize the UniformerAgent.

        Args:
            model_client: AutoGen ChatCompletionClient (e.g., UnstractAutogenBridge)
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="UniformerAgent",
            model_client=model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("Initialized UniformerAgent")

    async def uniformize_schemas(
        self, summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Harmonize field candidates from multiple document summaries.

        Args:
            summaries: List of summary dicts, each containing:
                - document_id: UUID
                - fields: List of field candidates from SummarizerAgent

        Returns:
            Dict with uniformized schema:
            {
                "fields": [...],
                "nested_objects": [...],
                "arrays": [...],
                "conflicts": [...],
                "uniform_schema_text": "..."  # Raw JSON for storage
            }
        """
        try:
            if not summaries:
                raise ValueError("No summaries provided")

            # Format summaries for the agent
            summary_text = self._format_summaries(summaries)

            # Create prompt
            user_message = f"""Analyze these document summaries and create a unified schema:

{summary_text}

Return the uniformized schema as JSON with fields, nested_objects, arrays, and conflicts."""

            # Send message to agent
            response = await self.agent.on_messages(
                [TextMessage(content=user_message, source="user")],
                cancellation_token=None,
            )

            # Extract response content
            if hasattr(response, "chat_message") and hasattr(
                response.chat_message, "content"
            ):
                response_text = response.chat_message.content
            else:
                response_text = str(response)

            # Parse JSON response
            try:
                # Clean response (remove markdown if present)
                cleaned = response_text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                uniform_schema = json.loads(cleaned)

                logger.info(
                    f"Uniformized schema: {len(uniform_schema.get('fields', []))} fields, "
                    f"{len(uniform_schema.get('conflicts', []))} conflicts"
                )

                # Add raw text for storage
                uniform_schema["uniform_schema_text"] = json.dumps(
                    uniform_schema, indent=2
                )

                return uniform_schema

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response was: {response_text}")
                # Return raw response with error
                return {
                    "fields": [],
                    "nested_objects": [],
                    "arrays": [],
                    "conflicts": [],
                    "uniform_schema_text": response_text,
                    "error": f"JSON parse error: {str(e)}",
                }

        except Exception as e:
            logger.error(f"Schema uniformization failed: {e}")
            raise

    def _format_summaries(self, summaries: List[Dict[str, Any]]) -> str:
        """Format summaries for agent input.

        Args:
            summaries: List of summary dicts

        Returns:
            Formatted text representation
        """
        lines = []
        lines.append(f"Total Documents: {len(summaries)}\n")

        for i, summary in enumerate(summaries, 1):
            doc_id = summary.get("document_id", f"doc-{i}")
            fields = summary.get("fields", [])

            lines.append(f"Document {i} (ID: {doc_id}):")
            lines.append(f"  Fields: {len(fields)}")

            for field in fields:
                name = field.get("name", "unknown")
                dtype = field.get("type", "string")
                desc = field.get("description", "")
                examples = field.get("examples", [])

                lines.append(f"    - {name} ({dtype}): {desc}")
                if examples:
                    # Ensure examples is a list before slicing
                    if isinstance(examples, list):
                        lines.append(f"      Examples: {', '.join(map(str, examples[:3]))}")
                    else:
                        lines.append(f"      Examples: {str(examples)}")

            lines.append("")

        return "\n".join(lines)

    def merge_field_examples(
        self, fields: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Merge examples from multiple instances of the same field.

        Args:
            fields: List of field dicts with same name

        Returns:
            Dict mapping field name to merged examples
        """
        examples_map = {}

        for field in fields:
            name = field.get("name")
            examples = field.get("examples", [])

            if name not in examples_map:
                examples_map[name] = []

            # Add unique examples
            for example in examples:
                if example not in examples_map[name]:
                    examples_map[name].append(example)

        return examples_map

    def detect_nested_structure(self, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect potential nested object structures from field names.

        Args:
            fields: List of field dicts

        Returns:
            Dict with suggested nested structure
        """
        nested_hints = {}

        for field in fields:
            name = field.get("name", "")

            # Look for common prefixes (customer_name, customer_address)
            if "_" in name:
                parts = name.split("_")
                if len(parts) >= 2:
                    prefix = parts[0]

                    if prefix not in nested_hints:
                        nested_hints[prefix] = []

                    nested_hints[prefix].append({
                        "original_name": name,
                        "nested_name": "_".join(parts[1:]),
                        "field": field,
                    })

        # Filter to only prefixes with 2+ fields
        nested_structure = {
            prefix: fields
            for prefix, fields in nested_hints.items()
            if len(fields) >= 2
        }

        return nested_structure

    def calculate_field_confidence(
        self, field_name: str, total_documents: int, appears_in: int
    ) -> str:
        """Calculate confidence level for a field.

        Args:
            field_name: Name of the field
            total_documents: Total number of documents
            appears_in: Number of documents where field appears

        Returns:
            Confidence level: "high", "medium", "low"
        """
        ratio = appears_in / total_documents if total_documents > 0 else 0

        if ratio >= 0.8:
            return "high"
        elif ratio >= 0.5:
            return "medium"
        else:
            return "low"
