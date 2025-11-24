"""EditorAgent for analyzing extraction failures and generating prompt improvements.

The EditorAgent analyzes field-level extraction failures and generates targeted
prompt edits to address specific error patterns without disrupting other fields.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge

logger = logging.getLogger(__name__)


class EditorAgent:
    """Agent that analyzes failures and generates surgical prompt edits.

    The EditorAgent receives:
    - Current extraction prompt
    - Field path that's failing (e.g., "invoice.customer_name")
    - List of failure examples with error classifications
    - Schema definition for the field

    It generates:
    - Targeted prompt edit (addition, modification, or clarification)
    - Explanation of the reasoning
    - Specific section to modify (field instruction, format requirement, etc.)
    """

    # System prompt that defines the editor's role and capabilities
    SYSTEM_PROMPT = """You are an expert prompt engineer specializing in data extraction optimization.

Your task is to analyze extraction failures for a specific field and generate SURGICAL prompt edits
that fix the issue without affecting other fields.

**Analysis Process:**
1. Review the current prompt and identify the field's extraction instructions
2. Analyze the failure patterns (truncation, format errors, missing data, etc.)
3. Review the verified/expected values to understand what was missed
4. Identify the root cause (ambiguous instructions, missing format specs, etc.)

**Edit Generation:**
- Generate MINIMAL, TARGETED edits (don't rewrite the entire prompt)
- Focus on the failing field's instructions
- Add specific format requirements if format errors are present
- Add length requirements if truncation is occurring
- Add examples if the field is complex or ambiguous
- Clarify extraction boundaries if data is being missed

**CRITICAL: You MUST respond with ONLY valid JSON, no other text or explanation.**

**Output Format (JSON only - no markdown, no explanation):**
{
  "edit_type": "add_instruction" | "modify_instruction" | "add_format_requirement" | "add_example",
  "target_section": "field_instruction" | "format_requirements" | "examples",
  "field_path": "the.field.path",
  "edit_text": "The exact text to add or the modified instruction",
  "reasoning": "Clear explanation of why this edit should fix the failures",
  "expected_improvement": "Description of what should improve"
}

**Important:**
- Keep edits focused and minimal
- Don't modify instructions for other fields
- Be specific about format requirements (e.g., "Extract full name including middle initial")
- Consider the error type when crafting the edit
- RESPOND WITH ONLY THE JSON OBJECT, nothing else
"""

    def __init__(self, model_client: UnstractAutogenBridge):
        """Initialize the EditorAgent.

        Args:
            model_client: UnstractAutogenBridge instance for LLM access
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="editor_agent",
            model_client=self.model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("EditorAgent initialized")

    async def edit_prompt(
        self,
        current_prompt: str,
        field_path: str,
        failures: List[Dict[str, Any]],
        schema: Dict[str, Any],
        error_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze failures and generate a targeted prompt edit.

        Args:
            current_prompt: The current extraction prompt text
            field_path: Dot-notation path of the failing field (e.g., "invoice.total")
            failures: List of failure examples, each containing:
                - document_id: ID of the document
                - extracted_value: What was extracted
                - verified_value: What should have been extracted
                - error_type: Classification of the error
            schema: JSON schema definition for the field
            error_type: Optional error type to focus on (if multiple types exist)

        Returns:
            Dictionary containing:
            - edit_type: Type of edit to apply
            - target_section: Which section of the prompt to modify
            - field_path: The field being addressed
            - edit_text: The actual text to add/modify
            - reasoning: Explanation of the edit
            - expected_improvement: What should improve
            - error: Error message if analysis failed
        """
        try:
            # Build context about the failures
            failure_summary = self._build_failure_summary(
                failures, field_path, error_type
            )

            # Extract field schema details
            field_schema = self._extract_field_schema(schema, field_path)

            # Build the analysis prompt
            analysis_prompt = f"""Analyze the following extraction failures and generate a targeted prompt edit.

**Current Prompt:**
```
{current_prompt}
```

**Failing Field:** {field_path}

**Field Schema:**
```json
{json.dumps(field_schema, indent=2)}
```

**Failure Analysis:**
{failure_summary}

Generate a JSON response with your proposed edit following the output format specified in your system prompt.
"""

            logger.info(f"Requesting prompt edit for field: {field_path}")

            # Call the agent
            response = await self.agent.on_messages(
                [TextMessage(content=analysis_prompt, source="user")],
                cancellation_token=None,
            )

            # Parse the response
            edit_result = self._parse_edit_response(response.chat_message.content)

            logger.info(
                f"Generated edit for {field_path}: {edit_result.get('edit_type')}"
            )

            return edit_result

        except Exception as e:
            logger.error(f"Failed to generate prompt edit for {field_path}: {e}")
            return {
                "error": str(e),
                "field_path": field_path,
                "edit_type": None,
            }

    def _build_failure_summary(
        self,
        failures: List[Dict[str, Any]],
        field_path: str,
        error_type: Optional[str] = None,
    ) -> str:
        """Build a readable summary of failures for the agent.

        Args:
            failures: List of failure dictionaries
            field_path: Field being analyzed
            error_type: Optional filter for specific error type

        Returns:
            Formatted string summary of failures
        """
        # Filter by error type if specified
        if error_type:
            failures = [f for f in failures if f.get("error_type") == error_type]

        if not failures:
            return "No failures provided for analysis."

        # Group failures by error type
        by_error_type: Dict[str, List[Dict]] = {}
        for failure in failures:
            err_type = failure.get("error_type", "unknown")
            if err_type not in by_error_type:
                by_error_type[err_type] = []
            by_error_type[err_type].append(failure)

        # Build summary
        lines = [f"Total Failures: {len(failures)}\n"]

        for err_type, examples in by_error_type.items():
            lines.append(f"\n**{err_type.upper()} ({len(examples)} occurrences)**")

            # Show up to 3 examples per error type
            for i, example in enumerate(examples[:3]):
                lines.append(f"\nExample {i+1}:")
                lines.append(f"  - Extracted: {example.get('extracted_value', 'N/A')}")
                lines.append(f"  - Expected: {example.get('verified_value', 'N/A')}")

                if example.get("document_id"):
                    lines.append(f"  - Document: {example['document_id']}")

            if len(examples) > 3:
                lines.append(f"\n  ... and {len(examples) - 3} more similar cases")

        return "\n".join(lines)

    def _extract_field_schema(
        self, schema: Dict[str, Any], field_path: str
    ) -> Dict[str, Any]:
        """Extract schema definition for a specific field path.

        Args:
            schema: Full JSON schema
            field_path: Dot-notation field path

        Returns:
            Schema definition for the specific field
        """
        try:
            # Split path into components
            path_parts = field_path.split(".")

            # Navigate through the schema
            current = schema.get("properties", {})
            field_schema = None

            for i, part in enumerate(path_parts):
                if part in current:
                    field_schema = current[part]

                    # If not the last part, navigate deeper
                    if i < len(path_parts) - 1:
                        if "properties" in field_schema:
                            current = field_schema["properties"]
                        elif "items" in field_schema:
                            # Handle array items
                            if "properties" in field_schema["items"]:
                                current = field_schema["items"]["properties"]
                            else:
                                break
                        else:
                            break
                else:
                    logger.warning(f"Field path {field_path} not found in schema")
                    break

            return field_schema or {"type": "string", "description": "Unknown field"}

        except Exception as e:
            logger.error(f"Failed to extract field schema for {field_path}: {e}")
            return {"type": "string", "description": "Unknown field"}

    def _parse_edit_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the agent's edit response.

        Args:
            response_text: Raw response from the agent

        Returns:
            Parsed edit dictionary
        """
        try:
            # Try direct JSON parsing
            cleaned = response_text.strip()

            # Remove markdown code blocks if present
            if cleaned.startswith("```"):
                # Remove ```json or ``` from start
                lines = cleaned.split("\n")
                if len(lines) > 2:
                    # Remove first line (```json or ```) and last line (```)
                    cleaned = "\n".join(lines[1:-1])
                elif len(lines) == 1:
                    # Single line with backticks - remove them
                    cleaned = cleaned.strip("`").strip()

            # Try to find JSON object in the response if direct parsing fails
            if not cleaned.startswith("{"):
                # Look for the first { and last }
                start_idx = cleaned.find("{")
                end_idx = cleaned.rfind("}")
                if start_idx >= 0 and end_idx > start_idx:
                    cleaned = cleaned[start_idx:end_idx + 1]

            # Handle empty or invalid response
            if not cleaned or cleaned == "":
                logger.error("Empty response from editor agent")
                logger.error(f"Raw response: {response_text}")
                return {
                    "error": "Empty response from editor agent",
                    "raw_response": response_text,
                    "edit_type": None,
                }

            # Parse JSON
            edit_result = json.loads(cleaned)

            # Validate required fields
            required_fields = [
                "edit_type",
                "target_section",
                "field_path",
                "edit_text",
                "reasoning",
            ]
            for field in required_fields:
                if field not in edit_result:
                    logger.warning(f"Missing required field in edit response: {field}")
                    edit_result[field] = None

            return edit_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse edit response as JSON: {e}")
            logger.error(f"Raw response: {response_text}")
            return {
                "error": "Failed to parse edit response",
                "raw_response": response_text,
                "edit_type": None,
            }

    def explain_edit(self, edit_result: Dict[str, Any]) -> str:
        """Generate a human-readable explanation of the edit.

        Args:
            edit_result: Edit result dictionary from edit_prompt()

        Returns:
            Human-readable explanation string
        """
        if edit_result.get("error"):
            return f"Error: {edit_result['error']}"

        explanation = f"""Prompt Edit Proposal for {edit_result.get('field_path')}:

Edit Type: {edit_result.get('edit_type')}
Target Section: {edit_result.get('target_section')}

Proposed Change:
{edit_result.get('edit_text')}

Reasoning:
{edit_result.get('reasoning')}

Expected Improvement:
{edit_result.get('expected_improvement', 'Not specified')}
"""
        return explanation
