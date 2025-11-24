"""CriticAgent for validating prompt edits and preventing side effects.

The CriticAgent acts as a quality gate, reviewing proposed prompt edits
to ensure they address the target issue without introducing regressions
or negatively impacting other fields.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge

logger = logging.getLogger(__name__)


class CriticAgent:
    """Agent that validates proposed prompt edits for quality and safety.

    The CriticAgent receives:
    - Original prompt
    - Proposed edit from EditorAgent
    - Schema for all fields (not just the failing one)
    - List of canary fields that must not regress

    It evaluates:
    - Will the edit fix the identified issue?
    - Could the edit negatively impact other fields?
    - Is the edit specific enough or too broad?
    - Does the edit maintain clarity and consistency?

    It returns:
    - Approval (APPROVE/REJECT/REVISE)
    - Reasoning for the decision
    - Suggested revisions if applicable
    """

    SYSTEM_PROMPT = """You are an expert prompt engineering reviewer specializing in quality assurance.

Your task is to critically evaluate proposed prompt edits to ensure they:
1. Address the identified extraction failure
2. Do NOT introduce side effects on other fields
3. Maintain prompt clarity and consistency
4. Are specific enough to fix the issue but not overly restrictive

**Evaluation Criteria:**

**APPROVE if:**
- The edit directly addresses the failure pattern
- The edit is surgical and field-specific
- The edit won't affect other field extractions
- The wording is clear and unambiguous
- Format requirements are well-defined

**REJECT if:**
- The edit is too broad and could affect multiple fields
- The edit introduces ambiguity or conflicting instructions
- The edit might cause canary fields to fail
- The reasoning doesn't match the proposed change
- The edit doesn't actually address the failure type

**REVISE if:**
- The direction is correct but wording needs refinement
- The edit is too aggressive and needs to be more targeted
- Additional constraints are needed for safety
- The edit could be simplified

**CRITICAL: You MUST respond with ONLY valid JSON, no other text or explanation.**

**Output Format (JSON only - no markdown, no explanation):**
{
  "decision": "APPROVE" | "REJECT" | "REVISE",
  "confidence": 0.0 to 1.0,
  "reasoning": "Detailed explanation of the decision",
  "concerns": ["List of potential issues or risks"],
  "revision_suggestion": "If REVISE, provide the improved version",
  "canary_risk": "low" | "medium" | "high" - Risk of affecting canary fields
}

Be thorough but fair. The goal is to improve extraction accuracy, not to block all changes.
RESPOND WITH ONLY THE JSON OBJECT, nothing else.
"""

    def __init__(self, model_client: UnstractAutogenBridge):
        """Initialize the CriticAgent.

        Args:
            model_client: UnstractAutogenBridge instance for LLM access
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="critic_agent",
            model_client=self.model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("CriticAgent initialized")

    async def review_edit(
        self,
        original_prompt: str,
        proposed_edit: Dict[str, Any],
        schema: Dict[str, Any],
        canary_fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Review a proposed prompt edit for quality and safety.

        Args:
            original_prompt: The current extraction prompt
            proposed_edit: Edit proposal from EditorAgent containing:
                - edit_type: Type of edit
                - target_section: Section to modify
                - field_path: Field being addressed
                - edit_text: Proposed text
                - reasoning: Editor's reasoning
            schema: Full JSON schema for all fields
            canary_fields: List of field paths that must not regress

        Returns:
            Dictionary containing:
            - decision: APPROVE, REJECT, or REVISE
            - confidence: 0.0 to 1.0 confidence in decision
            - reasoning: Explanation of the decision
            - concerns: List of potential issues
            - revision_suggestion: Improved version if REVISE
            - canary_risk: Risk level for canary fields
            - error: Error message if review failed
        """
        try:
            # Validate proposed edit
            if not proposed_edit or proposed_edit.get("error"):
                return {
                    "decision": "REJECT",
                    "reasoning": "Invalid or failed edit proposal",
                    "confidence": 1.0,
                }

            # Build review context
            canary_context = self._build_canary_context(canary_fields, schema)

            # Build the review prompt
            review_prompt = f"""Review the following proposed prompt edit for quality and safety.

**Original Prompt:**
```
{original_prompt}
```

**Proposed Edit:**
- Field Path: {proposed_edit.get('field_path')}
- Edit Type: {proposed_edit.get('edit_type')}
- Target Section: {proposed_edit.get('target_section')}

Edit Text:
```
{proposed_edit.get('edit_text')}
```

Editor's Reasoning:
{proposed_edit.get('reasoning')}

**Schema Context:**
```json
{json.dumps(schema, indent=2)}
```

**Canary Fields (must not regress):**
{canary_context}

Evaluate this edit and provide your decision in JSON format as specified in your system prompt.
Consider:
1. Does this edit directly address the identified failure?
2. Could this edit negatively impact other fields, especially canary fields?
3. Is the edit specific and targeted, or too broad?
4. Is the wording clear and unambiguous?
"""

            logger.info(
                f"Reviewing edit for field: {proposed_edit.get('field_path')}"
            )

            # Call the agent
            response = await self.agent.on_messages(
                [TextMessage(content=review_prompt, source="user")],
                cancellation_token=None,
            )

            # Parse the response
            review_result = self._parse_review_response(response.chat_message.content)

            logger.info(
                f"Review decision for {proposed_edit.get('field_path')}: "
                f"{review_result.get('decision')} "
                f"(confidence: {review_result.get('confidence', 0):.2f})"
            )

            return review_result

        except Exception as e:
            logger.error(f"Failed to review edit: {e}")
            return {
                "error": str(e),
                "decision": "REJECT",
                "reasoning": f"Review process failed: {str(e)}",
                "confidence": 0.0,
            }

    def _build_canary_context(
        self, canary_fields: Optional[List[str]], schema: Dict[str, Any]
    ) -> str:
        """Build context about canary fields.

        Args:
            canary_fields: List of canary field paths
            schema: Full schema

        Returns:
            Formatted string describing canary fields
        """
        if not canary_fields:
            return "No canary fields defined."

        lines = []
        for field_path in canary_fields:
            # Get field description from schema
            field_schema = self._extract_field_schema(schema, field_path)
            field_type = field_schema.get("type", "unknown")
            field_desc = field_schema.get("description", "No description")

            lines.append(f"- {field_path} ({field_type}): {field_desc}")

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
            path_parts = field_path.split(".")
            current = schema.get("properties", {})
            field_schema = None

            for i, part in enumerate(path_parts):
                if part in current:
                    field_schema = current[part]

                    if i < len(path_parts) - 1:
                        if "properties" in field_schema:
                            current = field_schema["properties"]
                        elif "items" in field_schema:
                            if "properties" in field_schema["items"]:
                                current = field_schema["items"]["properties"]
                            else:
                                break
                        else:
                            break
                else:
                    break

            return field_schema or {"type": "string", "description": "Unknown field"}

        except Exception as e:
            logger.error(f"Failed to extract field schema for {field_path}: {e}")
            return {"type": "string", "description": "Unknown field"}

    def _parse_review_response(self, response_text: str) -> Dict[str, Any]:
        """Parse the agent's review response.

        Args:
            response_text: Raw response from the agent

        Returns:
            Parsed review dictionary
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
                logger.error("Empty response from critic agent")
                logger.error(f"Raw response: {response_text}")
                return {
                    "decision": "REJECT",
                    "confidence": 0.0,
                    "reasoning": "Empty response from critic agent",
                    "concerns": ["No response received"],
                    "raw_response": response_text,
                }

            # Parse JSON
            review_result = json.loads(cleaned)

            # Validate required fields
            if "decision" not in review_result:
                review_result["decision"] = "REJECT"
                review_result["reasoning"] = "Invalid response format"

            # Ensure confidence is present and valid
            if "confidence" not in review_result:
                review_result["confidence"] = 0.5
            else:
                review_result["confidence"] = max(
                    0.0, min(1.0, float(review_result["confidence"]))
                )

            # Ensure concerns is a list
            if "concerns" not in review_result:
                review_result["concerns"] = []
            elif isinstance(review_result["concerns"], str):
                review_result["concerns"] = [review_result["concerns"]]

            # Set default canary risk if not present
            if "canary_risk" not in review_result:
                review_result["canary_risk"] = "medium"

            return review_result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse review response as JSON: {e}")
            logger.error(f"Raw response: {response_text}")
            return {
                "decision": "REJECT",
                "confidence": 0.0,
                "reasoning": "Failed to parse review response",
                "concerns": ["Invalid response format"],
                "raw_response": response_text,
            }
        except Exception as e:
            logger.error(f"Error parsing review response: {e}")
            return {
                "decision": "REJECT",
                "confidence": 0.0,
                "reasoning": f"Error during review: {str(e)}",
                "concerns": [str(e)],
            }

    def explain_decision(self, review_result: Dict[str, Any]) -> str:
        """Generate a human-readable explanation of the review decision.

        Args:
            review_result: Review result dictionary from review_edit()

        Returns:
            Human-readable explanation string
        """
        if review_result.get("error"):
            return f"Review Error: {review_result['error']}"

        decision = review_result.get("decision", "UNKNOWN")
        confidence = review_result.get("confidence", 0.0)

        explanation = f"""Review Decision: {decision} (Confidence: {confidence:.1%})

Reasoning:
{review_result.get('reasoning', 'No reasoning provided')}
"""

        if review_result.get("concerns"):
            explanation += "\nConcerns:\n"
            for concern in review_result["concerns"]:
                explanation += f"  - {concern}\n"

        if review_result.get("revision_suggestion"):
            explanation += f"\nSuggested Revision:\n{review_result['revision_suggestion']}\n"

        explanation += f"\nCanary Field Risk: {review_result.get('canary_risk', 'unknown').upper()}"

        return explanation

    def is_approved(self, review_result: Dict[str, Any]) -> bool:
        """Check if the review result is an approval.

        Args:
            review_result: Review result dictionary

        Returns:
            True if approved, False otherwise
        """
        return review_result.get("decision") == "APPROVE"

    def needs_revision(self, review_result: Dict[str, Any]) -> bool:
        """Check if the review result requires revision.

        Args:
            review_result: Review result dictionary

        Returns:
            True if revision needed, False otherwise
        """
        return review_result.get("decision") == "REVISE"
