"""SummarizerAgent: Extracts field candidates from documents.

This agent analyzes document text and identifies potential fields
for extraction along with their descriptions.
"""

import json
import logging
from typing import Any, Dict

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

logger = logging.getLogger(__name__)


class SummarizerAgent:
    """Agent that summarizes documents to extract field candidates.

    This agent:
    1. Analyzes document text
    2. Identifies extractable fields
    3. Describes each field's purpose and format
    4. Returns structured field candidates as JSON
    """

    SYSTEM_PROMPT = """You are a document analysis expert. Your task is to analyze a document and identify all fields that could be extracted.

IMPORTANT: Analyze the ACTUAL content of the document provided. Do NOT assume the document is an invoice or any specific type. Extract fields based solely on what you find in the document text.

For each field you identify in the document, provide:
1. Field name (snake_case) - based on what the field actually represents in the document
2. Description (what this field represents in the context of this specific document)
3. Data type (string, number, date, boolean, array, object)
4. Example values - actual values found in the document

Return ONLY a JSON array of field objects, no other text.

Output format:
[
    {
        "name": "actual_field_name_from_document",
        "description": "Description based on what this field represents in the document",
        "type": "string",
        "examples": ["actual_value_1", "actual_value_2"]
    }
]

CRITICAL:
- Only extract fields that actually exist in the provided document
- Do NOT invent fields like invoice_number, total_amount, customer_name unless they actually appear in the document
- Base all field names, descriptions, and examples on the actual document content
- Be thorough - extract all fields you can identify, including nested objects"""

    def __init__(self, model_client: ChatCompletionClient):
        """Initialize the SummarizerAgent.

        Args:
            model_client: AutoGen ChatCompletionClient (e.g., UnstractAutogenBridge)
        """
        self.model_client = model_client
        self.agent = AssistantAgent(
            name="SummarizerAgent",
            model_client=model_client,
            system_message=self.SYSTEM_PROMPT,
        )
        logger.info("Initialized SummarizerAgent")

    async def summarize_document(self, document_text: str) -> Dict[str, Any]:
        """Analyze document and extract field candidates.

        Args:
            document_text: Raw text from the document

        Returns:
            Dict with field candidates:
            {
                "fields": [...],
                "summary_text": "..."  # Raw JSON string for storage
            }
        """
        try:
            # Truncate very long documents to fit context
            max_chars = 8000
            if len(document_text) > max_chars:
                logger.warning(
                    f"Document too long ({len(document_text)} chars), truncating to {max_chars}"
                )
                document_text = document_text[:max_chars] + "\n... [truncated]"

            # Create prompt
            user_message = f"""Analyze this document and extract all possible fields:

---
{document_text}
---

Return the field candidates as a JSON array."""

            # Send message to agent
            response = await self.agent.on_messages(
                [TextMessage(content=user_message, source="user")], cancellation_token=None
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

                fields = json.loads(cleaned)

                logger.info(f"Extracted {len(fields)} field candidates")

                return {
                    "fields": fields,
                    "summary_text": json.dumps(fields, indent=2),
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.debug(f"Response was: {response_text}")
                # Return raw response as summary
                return {
                    "fields": [],
                    "summary_text": response_text,
                    "error": f"JSON parse error: {str(e)}",
                }

        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            raise

    def format_fields_as_text(self, fields: list) -> str:
        """Format field candidates as human-readable text.

        Args:
            fields: List of field dictionaries

        Returns:
            Formatted text summary
        """
        lines = []
        for field in fields:
            name = field.get("name", "unknown")
            desc = field.get("description", "")
            dtype = field.get("type", "string")
            examples = field.get("examples", [])

            lines.append(f"Field: {name}")
            lines.append(f"  Type: {dtype}")
            lines.append(f"  Description: {desc}")
            if examples:
                # Ensure examples is a list before slicing
                if isinstance(examples, list):
                    lines.append(f"  Examples: {', '.join(map(str, examples[:3]))}")
                else:
                    lines.append(f"  Examples: {str(examples)}")
            lines.append("")

        return "\n".join(lines)
