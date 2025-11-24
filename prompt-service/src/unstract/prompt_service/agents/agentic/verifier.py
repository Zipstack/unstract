"""VerifierAgent: Generates ground truth verified data from extracted data.

This agent takes extracted data and generates clean, verified ground truth
by validating, correcting, and standardizing the extracted values.
"""

import json
import logging
from typing import Any, Dict

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)


class VerifierAgent:
    """Agent that generates verified ground truth from extracted data.

    This agent:
    1. Analyzes extracted data from the document
    2. Validates field values against schema
    3. Corrects any extraction errors or inconsistencies
    4. Standardizes formats (dates, numbers, etc.)
    5. Returns clean ground truth data
    """

    SYSTEM_PROMPT = """You are a data verification expert. Your task is to review extracted data from a document and generate clean, verified ground truth.

Your responsibilities:
1. Review the extracted field values
2. Validate data types and formats
3. Correct obvious extraction errors or OCR mistakes
4. Standardize formats (dates to ISO format, numbers to consistent precision, etc.)
5. Remove any extraction artifacts or noise
6. Ensure data completeness and accuracy

Input format:
- document_text: The original document text
- extracted_data: JSON object with extracted field values
- schema: Expected field structure and types

Output format:
Return ONLY a clean JSON object with verified field values, matching the schema structure.

Example:
Input extracted_data: {"invoice_number": " INV-001 ", "total": "1,500.00 USD", "date": "01/15/2024"}
Output: {"invoice_number": "INV-001", "total": 1500.00, "date": "2024-01-15"}

Be precise and accurate. When in doubt, preserve the original extracted value rather than guessing."""

    def __init__(self, model_client: ChatCompletionClient):
        """Initialize the VerifierAgent.

        Args:
            model_client: AutoGen ChatCompletionClient (e.g., UnstractAutogenBridge)
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="VerifierAgent",
            model_client=model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("Initialized VerifierAgent")

    async def generate_verified_data(
        self,
        document_text: str,
        extracted_data: Dict[str, Any],
        schema: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Generate verified ground truth from extracted data.

        Args:
            document_text: Original document text for reference
            extracted_data: Raw extracted data to verify
            schema: Optional schema for validation

        Returns:
            Dict with verified data:
            {
                "data": {...},  # Verified field values
                "verification_notes": "..."  # Optional notes about corrections
            }
        """
        try:
            # Build context message
            context_parts = [
                "Please verify and clean the following extracted data:",
                "",
                "**Extracted Data:**",
                "```json",
                json.dumps(extracted_data, indent=2),
                "```",
            ]

            if schema:
                context_parts.extend(
                    [
                        "",
                        "**Expected Schema:**",
                        "```json",
                        json.dumps(schema, indent=2),
                        "```",
                    ]
                )

            # Truncate document text if too long
            max_text_chars = 4000
            doc_text_preview = document_text
            if len(document_text) > max_text_chars:
                doc_text_preview = (
                    document_text[:max_text_chars] + "\n... [truncated]"
                )
                logger.warning(
                    f"Document text truncated from {len(document_text)} to {max_text_chars} chars"
                )

            context_parts.extend(
                [
                    "",
                    "**Document Text (for reference):**",
                    "```",
                    doc_text_preview,
                    "```",
                    "",
                    "Return the verified data as a clean JSON object. Fix any extraction errors, standardize formats, and ensure accuracy.",
                ]
            )

            user_message = "\n".join(context_parts)

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
                # Clean response (remove markdown code blocks if present)
                cleaned = response_text.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.startswith("```"):
                    cleaned = cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                verified_data = json.loads(cleaned)

                logger.info(f"Generated verified data with {len(verified_data)} fields")

                return {
                    "data": verified_data,
                    "verification_notes": "Generated by LLM verification agent",
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse verified data JSON: {e}")
                logger.debug(f"Response was: {response_text}")
                # Return original data as fallback
                return {
                    "data": extracted_data,
                    "verification_notes": f"Verification failed (JSON parse error), using original extracted data",
                    "error": f"JSON parse error: {str(e)}",
                }

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            raise
