"""FinalizerAgent: Converts uniformized schema to valid JSON Schema.

This agent takes the uniformized schema and produces a final,
production-ready JSON Schema that can be used for extraction validation.
"""

import json
import logging
from typing import Any, Dict

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)


class FinalizerAgent:
    """Agent that produces final JSON Schema from uniformized schema.

    This agent:
    1. Takes uniformized schema from UniformerAgent
    2. Converts to valid JSON Schema (Draft 7)
    3. Adds proper type definitions and constraints
    4. Sets up nested objects and arrays correctly
    5. Adds descriptions and examples
    6. Ensures schema is production-ready
    """

    SYSTEM_PROMPT = """You are a JSON Schema expert. Your task is to convert a uniformized schema into a valid, production-ready JSON Schema (Draft 7).

Your responsibilities:
1. **Create Valid JSON Schema**: Follow JSON Schema Draft 7 specification
2. **Set Proper Types**: Use correct JSON Schema types (string, number, integer, boolean, array, object, null)
3. **Define Nested Objects**: Properly structure nested properties
4. **Define Arrays**: Set up array items with correct schemas
5. **Add Constraints**: Include appropriate constraints (minLength, maxLength, pattern, etc.)
6. **Add Metadata**: Include title, description, examples for all fields
7. **Make it Extraction-Ready**: Schema should guide LLM extraction

JSON Schema Template:
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "title": "Document Extraction Schema",
    "description": "Schema for extracting structured data from documents",
    "properties": {
        "invoice_number": {
            "type": "string",
            "description": "Unique invoice identifier",
            "examples": ["INV-001", "INV-002"]
        },
        "date": {
            "type": "string",
            "format": "date",
            "description": "Invoice date in YYYY-MM-DD format",
            "examples": ["2025-01-14"]
        },
        "total_amount": {
            "type": "number",
            "description": "Total invoice amount",
            "minimum": 0,
            "examples": [1500.00, 2300.50]
        },
        "customer": {
            "type": "object",
            "description": "Customer information",
            "properties": {
                "name": {"type": "string", "description": "Customer name"},
                "address": {"type": "string", "description": "Customer address"}
            },
            "required": ["name"]
        },
        "line_items": {
            "type": "array",
            "description": "Invoice line items",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "total": {"type": "number"}
                },
                "required": ["description", "quantity", "unit_price", "total"]
            }
        }
    },
    "required": ["invoice_number", "date", "total_amount"]
}

Best Practices:
- Mark essential fields as "required"
- Use "format" for dates, emails, URLs
- Add constraints for numbers (minimum, maximum)
- Add patterns for strings (e.g., invoice number format)
- Keep descriptions clear and helpful for LLM extraction
- Include multiple examples per field

Return ONLY the JSON Schema, no other text."""

    def __init__(self, model_client: ChatCompletionClient):
        """Initialize the FinalizerAgent.

        Args:
            model_client: AutoGen ChatCompletionClient (e.g., UnstractAutogenBridge)
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="FinalizerAgent",
            model_client=model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("Initialized FinalizerAgent")

    async def finalize_schema(self, uniform_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert uniformized schema to final JSON Schema.

        Args:
            uniform_schema: Output from UniformerAgent containing:
                - fields: List of top-level fields
                - nested_objects: List of nested object definitions
                - arrays: List of array definitions
                - conflicts: Any conflicts encountered

        Returns:
            Dict with final JSON Schema:
            {
                "json_schema": {...},  # Valid JSON Schema object
                "json_schema_text": "...",  # JSON string for storage
                "statistics": {...}  # Schema statistics
            }
        """
        try:
            # Format uniform schema for the agent
            schema_description = self._format_uniform_schema(uniform_schema)

            # Create prompt
            user_message = f"""Convert this uniformized schema to a valid JSON Schema (Draft 7):

{schema_description}

Return the complete JSON Schema with proper structure, types, descriptions, and examples."""

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

            # Parse JSON Schema
            try:
                # Clean response
                cleaned = response_text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                json_schema = json.loads(cleaned)

                # Validate it's a proper JSON Schema
                if "$schema" not in json_schema:
                    json_schema["$schema"] = "http://json-schema.org/draft-07/schema#"
                if "type" not in json_schema:
                    json_schema["type"] = "object"

                # Calculate statistics
                stats = self._calculate_schema_stats(json_schema)

                logger.info(
                    f"Finalized JSON Schema: {stats['total_fields']} fields, "
                    f"{stats['required_fields']} required, "
                    f"{stats['nested_objects']} nested objects"
                )

                return {
                    "json_schema": json_schema,
                    "json_schema_text": json.dumps(json_schema, indent=2),
                    "statistics": stats,
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON Schema: {e}")
                logger.debug(f"Response was: {response_text}")
                # Return error response
                return {
                    "json_schema": {},
                    "json_schema_text": response_text,
                    "statistics": {},
                    "error": f"JSON parse error: {str(e)}",
                }

        except Exception as e:
            logger.error(f"Schema finalization failed: {e}")
            raise

    def _format_uniform_schema(self, uniform_schema: Dict[str, Any]) -> str:
        """Format uniformized schema for agent input.

        Args:
            uniform_schema: Uniformized schema from UniformerAgent

        Returns:
            Formatted text description
        """
        lines = []

        # Top-level fields
        fields = uniform_schema.get("fields", [])
        if fields:
            lines.append("## Top-Level Fields")
            for field in fields:
                name = field.get("name")
                dtype = field.get("type", "string")
                desc = field.get("description", "")
                examples = field.get("examples", [])
                confidence = field.get("confidence", "unknown")

                lines.append(f"- **{name}** ({dtype})")
                lines.append(f"  Description: {desc}")
                lines.append(f"  Confidence: {confidence}")
                if examples:
                    lines.append(f"  Examples: {', '.join(map(str, examples[:5]))}")
                lines.append("")

        # Nested objects
        nested_objects = uniform_schema.get("nested_objects", [])
        if nested_objects:
            lines.append("## Nested Objects")
            for obj in nested_objects:
                obj_name = obj.get("name")
                obj_fields = obj.get("fields", [])

                lines.append(f"- **{obj_name}** (object with {len(obj_fields)} fields)")
                for field in obj_fields:
                    lines.append(f"  - {field.get('name')} ({field.get('type')}): {field.get('description', '')}")
                lines.append("")

        # Arrays
        arrays = uniform_schema.get("arrays", [])
        if arrays:
            lines.append("## Arrays")
            for arr in arrays:
                arr_name = arr.get("name")
                item_schema = arr.get("item_schema", {})

                lines.append(f"- **{arr_name}** (array of objects)")
                lines.append(f"  Item Schema: {json.dumps(item_schema, indent=2)}")
                lines.append("")

        # Conflicts (informational)
        conflicts = uniform_schema.get("conflicts", [])
        if conflicts:
            lines.append("## Conflicts Resolved")
            for conflict in conflicts:
                lines.append(f"- Field: {conflict.get('field')}")
                lines.append(f"  Issue: {conflict.get('issue')}")
                lines.append(f"  Resolution: {conflict.get('resolution')}")
                lines.append("")

        return "\n".join(lines)

    def _calculate_schema_stats(self, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate statistics about the JSON Schema.

        Args:
            json_schema: Final JSON Schema object

        Returns:
            Dict with statistics
        """
        stats = {
            "total_fields": 0,
            "required_fields": 0,
            "nested_objects": 0,
            "arrays": 0,
            "max_depth": 0,
        }

        def count_fields(schema: Dict, depth: int = 0):
            """Recursively count fields."""
            stats["max_depth"] = max(stats["max_depth"], depth)

            properties = schema.get("properties", {})
            stats["total_fields"] += len(properties)

            required = schema.get("required", [])
            stats["required_fields"] += len(required)

            for field_name, field_schema in properties.items():
                field_type = field_schema.get("type")

                if field_type == "object":
                    stats["nested_objects"] += 1
                    count_fields(field_schema, depth + 1)

                elif field_type == "array":
                    stats["arrays"] += 1
                    items = field_schema.get("items", {})
                    if items.get("type") == "object":
                        count_fields(items, depth + 1)

        if json_schema.get("type") == "object":
            count_fields(json_schema)

        return stats

    def validate_json_schema(self, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the JSON Schema for common issues.

        Args:
            json_schema: JSON Schema to validate

        Returns:
            Dict with validation results:
            {
                "valid": bool,
                "errors": [str],
                "warnings": [str]
            }
        """
        errors = []
        warnings = []

        # Check required fields
        if "$schema" not in json_schema:
            warnings.append("Missing $schema field")

        if "type" not in json_schema:
            errors.append("Missing type field")

        if json_schema.get("type") == "object":
            if "properties" not in json_schema:
                warnings.append("Object type but no properties defined")

        # Check for descriptions
        properties = json_schema.get("properties", {})
        fields_without_description = [
            name for name, schema in properties.items()
            if "description" not in schema
        ]
        if fields_without_description:
            warnings.append(
                f"{len(fields_without_description)} fields missing descriptions: "
                f"{', '.join(fields_without_description[:5])}"
            )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
