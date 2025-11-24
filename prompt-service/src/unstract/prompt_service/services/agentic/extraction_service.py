"""ExtractionService: Extracts structured data from documents using LLMs.

This service handles the actual data extraction using generated prompts,
validates outputs against JSON schemas, and handles parsing errors.
"""

import json
import logging
from typing import Any, Dict, Optional

from json_repair import repair_json

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for extracting structured data from documents using LLM prompts.

    This service:
    1. Combines extraction prompt with document text
    2. Calls LLM via UnstractAutogenBridge
    3. Parses JSON response (with repair if needed)
    4. Validates against JSON Schema
    5. Returns extracted data with metadata
    """

    def __init__(self, llm_bridge: UnstractAutogenBridge):
        """Initialize extraction service.

        Args:
            llm_bridge: UnstractAutogenBridge for LLM calls
        """
        self.llm_bridge = llm_bridge
        logger.info("Initialized ExtractionService")

    async def extract_from_document(
        self,
        document_text: str,
        prompt_text: str,
        json_schema: Dict[str, Any],
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract structured data from document using prompt.

        Args:
            document_text: Raw text from document (from LLMWhisperer)
            prompt_text: Extraction prompt (from PromptArchitectAgent)
            json_schema: Expected JSON Schema for validation
            document_id: Optional document ID for logging

        Returns:
            Dict with extraction results:
            {
                "extracted_data": {...},  # Parsed JSON data
                "raw_response": "...",  # Raw LLM response
                "validation_errors": [...],  # Schema validation errors
                "metadata": {
                    "tokens_used": int,
                    "parse_method": "direct|repaired|fallback",
                    "extraction_time": float
                }
            }
        """
        try:
            import time
            start_time = time.time()

            # Prepare the full extraction prompt
            full_prompt = self._prepare_prompt(prompt_text, document_text)

            # Call LLM
            logger.info(f"Extracting from document {document_id or 'unknown'}")
            logger.debug(f"Prompt length: {len(full_prompt)} chars")

            # Use the LLM bridge to get completion
            # Note: We'll use direct LLM call, not agent-based
            response = await self._call_llm(full_prompt)

            extraction_time = time.time() - start_time

            # Parse JSON response
            extracted_data, parse_method = self._parse_response(response["content"])

            # Validate against schema
            validation_errors = self._validate_against_schema(
                extracted_data, json_schema
            )

            # Log results
            if validation_errors:
                logger.warning(
                    f"Extraction validation errors for {document_id}: "
                    f"{len(validation_errors)} errors"
                )
            else:
                logger.info(f"Successfully extracted from {document_id}")

            return {
                "extracted_data": extracted_data,
                "raw_response": response["content"],
                "validation_errors": validation_errors,
                "metadata": {
                    "tokens_used": response["usage"]["total_tokens"],
                    "prompt_tokens": response["usage"]["prompt_tokens"],
                    "completion_tokens": response["usage"]["completion_tokens"],
                    "parse_method": parse_method,
                    "extraction_time": extraction_time,
                    "document_id": document_id,
                },
            }

        except Exception as e:
            logger.error(f"Extraction failed for {document_id}: {e}")
            raise

    def _prepare_prompt(self, prompt_template: str, document_text: str) -> str:
        """Prepare the complete extraction prompt.

        Args:
            prompt_template: Prompt from PromptArchitectAgent
            document_text: Document text to extract from

        Returns:
            Complete prompt with document text inserted
        """
        # The prompt template should have a placeholder for document text
        # If it has {document_text}, replace it
        if "{document_text}" in prompt_template:
            return prompt_template.replace("{document_text}", document_text)

        # Otherwise, append document text at the end
        return f"{prompt_template}\n\n## Document Text\n{document_text}\n\n## Your Response\nPlease extract the data as JSON:"

    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Call LLM via bridge.

        Args:
            prompt: Complete extraction prompt

        Returns:
            Dict with response content and usage
        """
        from autogen_core.models import UserMessage

        # Create message
        message = UserMessage(content=prompt, source="user")

        # Call LLM via bridge
        result = await self.llm_bridge.create(
            messages=[message],
            temperature=0.0,  # Deterministic for extraction
            max_tokens=4096,  # Enough for large JSON responses
        )

        return {
            "content": result.content,
            "usage": {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": (
                    result.usage.prompt_tokens + result.usage.completion_tokens
                ),
            },
        }

    def _parse_response(self, response: str) -> tuple[Dict[str, Any], str]:
        """Parse JSON from LLM response.

        Tries multiple methods:
        1. Direct JSON parse
        2. Extract from markdown code blocks
        3. Repair malformed JSON
        4. Fallback to empty dict

        Args:
            response: Raw LLM response

        Returns:
            Tuple of (parsed_data, parse_method)
        """
        # Method 1: Direct parse
        try:
            data = json.loads(response)
            return data, "direct"
        except json.JSONDecodeError:
            pass

        # Method 2: Extract from code blocks
        try:
            cleaned = response.strip()
            if "```json" in cleaned:
                # Extract content between ```json and ```
                start = cleaned.find("```json") + 7
                end = cleaned.find("```", start)
                json_str = cleaned[start:end].strip()
                data = json.loads(json_str)
                return data, "code_block"
            elif "```" in cleaned:
                # Try generic code block
                start = cleaned.find("```") + 3
                end = cleaned.find("```", start)
                json_str = cleaned[start:end].strip()
                data = json.loads(json_str)
                return data, "code_block"
        except (json.JSONDecodeError, ValueError):
            pass

        # Method 3: Repair malformed JSON
        try:
            repaired = repair_json(response)
            data = json.loads(repaired)
            logger.warning("Used JSON repair to parse response")
            return data, "repaired"
        except Exception as e:
            logger.error(f"JSON repair failed: {e}")

        # Method 4: Fallback
        logger.error("Could not parse JSON response, returning empty dict")
        logger.debug(f"Response was: {response[:500]}...")
        return {}, "fallback"

    def _validate_against_schema(
        self, data: Dict[str, Any], json_schema: Dict[str, Any]
    ) -> list:
        """Validate extracted data against JSON Schema.

        Args:
            data: Extracted data
            json_schema: JSON Schema to validate against

        Returns:
            List of validation errors (empty if valid)
        """
        try:
            from jsonschema import validate, ValidationError

            try:
                validate(instance=data, schema=json_schema)
                return []
            except ValidationError as e:
                # Collect all validation errors
                errors = [
                    {
                        "message": e.message,
                        "path": list(e.path),
                        "schema_path": list(e.schema_path),
                    }
                ]
                return errors

        except ImportError:
            logger.warning("jsonschema not installed, skipping validation")
            return []
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return [{"message": f"Validation error: {str(e)}"}]

    async def batch_extract(
        self,
        documents: list[Dict[str, str]],
        prompt_text: str,
        json_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Extract from multiple documents in batch.

        Args:
            documents: List of dicts with 'id' and 'text'
            prompt_text: Extraction prompt
            json_schema: JSON Schema for validation

        Returns:
            Dict with batch results:
            {
                "total": int,
                "successful": int,
                "failed": int,
                "results": [...]
            }
        """
        results = []
        successful = 0
        failed = 0

        for doc in documents:
            doc_id = doc.get("id", "unknown")
            doc_text = doc.get("text", "")

            try:
                result = await self.extract_from_document(
                    document_text=doc_text,
                    prompt_text=prompt_text,
                    json_schema=json_schema,
                    document_id=doc_id,
                )

                # Check if extraction was successful
                if result["metadata"]["parse_method"] != "fallback":
                    successful += 1
                else:
                    failed += 1

                results.append(
                    {
                        "document_id": doc_id,
                        "status": "success" if result["extracted_data"] else "failed",
                        "data": result["extracted_data"],
                        "metadata": result["metadata"],
                    }
                )

            except Exception as e:
                logger.error(f"Batch extraction failed for {doc_id}: {e}")
                failed += 1
                results.append(
                    {
                        "document_id": doc_id,
                        "status": "error",
                        "error": str(e),
                    }
                )

        logger.info(
            f"Batch extraction complete: {successful}/{len(documents)} successful"
        )

        return {
            "total": len(documents),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

    def extract_single_field(
        self, extracted_data: Dict[str, Any], field_path: str
    ) -> Any:
        """Extract a single field value from nested JSON using dot notation.

        Args:
            extracted_data: Full extracted JSON
            field_path: Dot-separated path (e.g., "customer.address.city")

        Returns:
            Field value or None if not found
        """
        parts = field_path.split(".")
        current = extracted_data

        for part in parts:
            # Handle array notation (e.g., "items[0]")
            if "[" in part and "]" in part:
                field_name = part[: part.index("[")]
                index = int(part[part.index("[") + 1 : part.index("]")])

                if isinstance(current, dict) and field_name in current:
                    current = current[field_name]
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                else:
                    return None
            else:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None

        return current
