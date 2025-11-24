"""GuardAgent for testing prompt edits against canary fields.

The GuardAgent acts as a safety mechanism, testing proposed prompt edits
against high-value canary fields to ensure no regression occurs on
critical extractions.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge
from unstract.prompt_service.services.agentic.extraction_service import (
    ExtractionService,
)

logger = logging.getLogger(__name__)


class GuardAgent:
    """Agent that tests prompt edits against canary fields to prevent regression.

    The GuardAgent receives:
    - Original prompt
    - Edited prompt (with proposed changes applied)
    - List of canary field paths
    - Sample documents with verified data for canary fields
    - JSON schema

    It tests:
    - Does the edited prompt still correctly extract canary fields?
    - Is accuracy maintained or improved on canary fields?
    - Are there any new errors introduced on canary fields?

    It returns:
    - PASS/FAIL decision
    - Canary field test results
    - Comparison of original vs edited prompt on canary fields
    """

    def __init__(self, model_client: UnstractAutogenBridge):
        """Initialize the GuardAgent.

        Args:
            model_client: UnstractAutogenBridge instance for LLM access
        """
        self.model_client = model_client
        self.extraction_service = ExtractionService(model_client)
        logger.info("GuardAgent initialized")

    async def test_canary_fields(
        self,
        original_prompt: str,
        edited_prompt: str,
        canary_fields: List[str],
        test_documents: List[Dict[str, Any]],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Test edited prompt against canary fields.

        Args:
            original_prompt: The current extraction prompt
            edited_prompt: The proposed edited prompt
            canary_fields: List of field paths to protect (e.g., ["invoice.total"])
            test_documents: List of test documents, each containing:
                - document_id: ID of the document
                - document_text: Text content
                - verified_data: Known correct extraction for canary fields
            schema: JSON schema for validation

        Returns:
            Dictionary containing:
            - decision: PASS or FAIL
            - overall_accuracy: Accuracy on canary fields with edited prompt
            - original_accuracy: Accuracy with original prompt (for comparison)
            - field_results: Per-field test results
            - regressions: List of fields that got worse
            - improvements: List of fields that got better
            - error: Error message if testing failed
        """
        try:
            if not canary_fields:
                logger.warning("No canary fields specified, auto-passing")
                return {
                    "decision": "PASS",
                    "reasoning": "No canary fields to test",
                    "overall_accuracy": 1.0,
                }

            if not test_documents:
                logger.warning("No test documents provided, auto-passing")
                return {
                    "decision": "PASS",
                    "reasoning": "No test documents available",
                    "overall_accuracy": 1.0,
                }

            logger.info(
                f"Testing {len(canary_fields)} canary fields on {len(test_documents)} documents"
            )

            # Extract with both prompts
            original_results = await self._extract_with_prompt(
                original_prompt, test_documents, schema
            )

            edited_results = await self._extract_with_prompt(
                edited_prompt, test_documents, schema
            )

            # Compare results on canary fields only
            field_results = []
            regressions = []
            improvements = []

            for field_path in canary_fields:
                field_result = self._compare_field_results(
                    field_path,
                    original_results,
                    edited_results,
                    test_documents,
                )

                field_results.append(field_result)

                # Track regressions and improvements
                if field_result["changed"]:
                    if field_result["edited_accuracy"] < field_result["original_accuracy"]:
                        regressions.append(
                            {
                                "field_path": field_path,
                                "accuracy_drop": field_result["original_accuracy"]
                                - field_result["edited_accuracy"],
                            }
                        )
                    elif field_result["edited_accuracy"] > field_result["original_accuracy"]:
                        improvements.append(
                            {
                                "field_path": field_path,
                                "accuracy_gain": field_result["edited_accuracy"]
                                - field_result["original_accuracy"],
                            }
                        )

            # Calculate overall accuracy
            total_tests = len(canary_fields) * len(test_documents)
            original_correct = sum(
                r["original_correct"] * len(test_documents) for r in field_results
            )
            edited_correct = sum(
                r["edited_correct"] * len(test_documents) for r in field_results
            )

            original_accuracy = original_correct / total_tests if total_tests > 0 else 0
            edited_accuracy = edited_correct / total_tests if total_tests > 0 else 0

            # Determine PASS/FAIL
            # FAIL if any regressions occurred
            decision = "FAIL" if regressions else "PASS"

            reasoning = self._build_reasoning(
                decision, regressions, improvements, original_accuracy, edited_accuracy
            )

            logger.info(
                f"Canary test {decision}: "
                f"Original accuracy: {original_accuracy:.1%}, "
                f"Edited accuracy: {edited_accuracy:.1%}"
            )

            return {
                "decision": decision,
                "reasoning": reasoning,
                "overall_accuracy": edited_accuracy,
                "original_accuracy": original_accuracy,
                "field_results": field_results,
                "regressions": regressions,
                "improvements": improvements,
                "canary_fields_tested": len(canary_fields),
                "documents_tested": len(test_documents),
            }

        except Exception as e:
            logger.error(f"Failed to test canary fields: {e}")
            return {
                "error": str(e),
                "decision": "FAIL",
                "reasoning": f"Testing failed: {str(e)}",
                "overall_accuracy": 0.0,
            }

    async def _extract_with_prompt(
        self,
        prompt: str,
        test_documents: List[Dict[str, Any]],
        schema: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract data from documents using a specific prompt.

        Args:
            prompt: Extraction prompt to use
            test_documents: List of test documents
            schema: JSON schema

        Returns:
            List of extraction results
        """
        results = []

        for doc in test_documents:
            try:
                extraction_result = await self.extraction_service.extract_from_document(
                    document_text=doc["document_text"],
                    prompt_text=prompt,
                    json_schema=schema,
                    document_id=doc.get("document_id"),
                )

                results.append(
                    {
                        "document_id": doc.get("document_id"),
                        "extracted_data": extraction_result["extracted_data"],
                        "verified_data": doc.get("verified_data", {}),
                    }
                )

            except Exception as e:
                logger.error(
                    f"Extraction failed for document {doc.get('document_id')}: {e}"
                )
                results.append(
                    {
                        "document_id": doc.get("document_id"),
                        "extracted_data": {},
                        "verified_data": doc.get("verified_data", {}),
                        "error": str(e),
                    }
                )

        return results

    def _compare_field_results(
        self,
        field_path: str,
        original_results: List[Dict[str, Any]],
        edited_results: List[Dict[str, Any]],
        test_documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare extraction results for a specific field.

        Args:
            field_path: Dot-notation field path
            original_results: Results with original prompt
            edited_results: Results with edited prompt
            test_documents: Original test documents with verified data

        Returns:
            Comparison results for the field
        """
        original_correct = 0
        edited_correct = 0
        total = len(test_documents)

        for i, doc in enumerate(test_documents):
            verified_data = doc.get("verified_data", {})
            verified_value = self._get_nested_value(verified_data, field_path)

            # Get original and edited values
            original_value = self._get_nested_value(
                original_results[i]["extracted_data"], field_path
            )
            edited_value = self._get_nested_value(
                edited_results[i]["extracted_data"], field_path
            )

            # Normalize and compare
            verified_norm = self._normalize_value(verified_value)
            original_norm = self._normalize_value(original_value)
            edited_norm = self._normalize_value(edited_value)

            if original_norm == verified_norm:
                original_correct += 1
            if edited_norm == verified_norm:
                edited_correct += 1

        original_accuracy = original_correct / total if total > 0 else 0
        edited_accuracy = edited_correct / total if total > 0 else 0

        return {
            "field_path": field_path,
            "original_accuracy": original_accuracy,
            "edited_accuracy": edited_accuracy,
            "original_correct": original_correct,
            "edited_correct": edited_correct,
            "total_tests": total,
            "changed": original_accuracy != edited_accuracy,
        }

    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get value from nested dictionary using dot notation.

        Args:
            data: Dictionary to extract from
            field_path: Dot-notation path (e.g., "invoice.customer.name")

        Returns:
            Value at the path, or None if not found
        """
        if not data:
            return None

        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _normalize_value(self, value: Any) -> str:
        """Normalize a value for comparison.

        Args:
            value: Value to normalize

        Returns:
            Normalized string representation
        """
        if value is None:
            return ""

        if isinstance(value, (int, float)):
            return str(value).strip()

        if isinstance(value, str):
            return value.lower().strip()

        # For other types, convert to JSON
        return json.dumps(value, sort_keys=True)

    def _build_reasoning(
        self,
        decision: str,
        regressions: List[Dict],
        improvements: List[Dict],
        original_accuracy: float,
        edited_accuracy: float,
    ) -> str:
        """Build human-readable reasoning for the decision.

        Args:
            decision: PASS or FAIL
            regressions: List of regressed fields
            improvements: List of improved fields
            original_accuracy: Original canary accuracy
            edited_accuracy: Edited canary accuracy

        Returns:
            Reasoning string
        """
        lines = []

        if decision == "FAIL":
            lines.append(f"FAILED: Canary field regression detected.")
            lines.append(
                f"Overall canary accuracy dropped from {original_accuracy:.1%} "
                f"to {edited_accuracy:.1%}"
            )

            if regressions:
                lines.append("\nRegressed fields:")
                for reg in regressions:
                    lines.append(
                        f"  - {reg['field_path']}: "
                        f"accuracy dropped by {reg['accuracy_drop']:.1%}"
                    )
        else:
            lines.append(f"PASSED: No canary field regressions detected.")
            lines.append(
                f"Overall canary accuracy: {original_accuracy:.1%} → {edited_accuracy:.1%}"
            )

            if improvements:
                lines.append("\nImproved fields:")
                for imp in improvements:
                    lines.append(
                        f"  - {imp['field_path']}: "
                        f"accuracy improved by {imp['accuracy_gain']:.1%}"
                    )

        return "\n".join(lines)

    def explain_results(self, guard_result: Dict[str, Any]) -> str:
        """Generate a human-readable explanation of guard test results.

        Args:
            guard_result: Guard result dictionary from test_canary_fields()

        Returns:
            Human-readable explanation string
        """
        if guard_result.get("error"):
            return f"Guard Test Error: {guard_result['error']}"

        decision = guard_result.get("decision", "UNKNOWN")
        reasoning = guard_result.get("reasoning", "No reasoning provided")

        explanation = f"""Guard Test Result: {decision}

{reasoning}

Canary Fields Tested: {guard_result.get('canary_fields_tested', 0)}
Documents Tested: {guard_result.get('documents_tested', 0)}
"""

        return explanation
