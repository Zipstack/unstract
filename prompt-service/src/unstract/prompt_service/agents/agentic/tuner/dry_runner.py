"""DryRunnerAgent for testing prompt edits on sample documents.

The DryRunnerAgent tests edited prompts on actual failing documents
to measure whether the edit improves extraction accuracy for the
target field without introducing new errors.
"""

import logging
from typing import Any, Dict, List

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge
from unstract.prompt_service.services.agentic.comparison_service import (
    ComparisonService,
)
from unstract.prompt_service.services.agentic.extraction_service import (
    ExtractionService,
)

logger = logging.getLogger(__name__)


class DryRunnerAgent:
    """Agent that tests prompt edits on sample documents to measure improvement.

    The DryRunnerAgent receives:
    - Original prompt
    - Edited prompt (with proposed changes applied)
    - Target field path that was failing
    - Sample documents where the field was failing
    - Verified data for comparison

    It tests:
    - Does the edited prompt fix the failing field?
    - What is the success rate improvement on the target field?
    - Are there any new errors introduced on other fields?

    It returns:
    - Success rate on target field (original vs edited)
    - Overall accuracy change
    - Per-document comparison results
    - Recommendation (ACCEPT/REJECT based on improvement threshold)
    """

    # Minimum improvement threshold to recommend acceptance
    MIN_IMPROVEMENT_THRESHOLD = 0.1  # 10% improvement required

    def __init__(self, model_client: UnstractAutogenBridge):
        """Initialize the DryRunnerAgent.

        Args:
            model_client: UnstractAutogenBridge instance for LLM access
        """
        self.model_client = model_client
        self.extraction_service = ExtractionService(model_client)
        self.comparison_service = ComparisonService(model_client)
        logger.info("DryRunnerAgent initialized")

    async def test_edit(
        self,
        original_prompt: str,
        edited_prompt: str,
        target_field: str,
        test_documents: List[Dict[str, Any]],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Test edited prompt on sample documents to measure improvement.

        Args:
            original_prompt: The current extraction prompt
            edited_prompt: The proposed edited prompt
            target_field: Field path that was failing (e.g., "invoice.customer_name")
            test_documents: List of test documents, each containing:
                - document_id: ID of the document
                - document_text: Text content
                - verified_data: Known correct extraction data
            schema: JSON schema for validation

        Returns:
            Dictionary containing:
            - recommendation: ACCEPT or REJECT
            - target_field_improvement: Accuracy improvement on target field
            - original_target_accuracy: Accuracy with original prompt
            - edited_target_accuracy: Accuracy with edited prompt
            - overall_accuracy_change: Change in overall accuracy
            - document_results: Per-document comparison
            - new_errors: Any new errors introduced on other fields
            - error: Error message if testing failed
        """
        try:
            if not test_documents:
                logger.warning("No test documents provided")
                return {
                    "recommendation": "REJECT",
                    "reasoning": "No test documents available for dry run",
                }

            logger.info(
                f"Dry run test: {len(test_documents)} documents, target field: {target_field}"
            )

            # Extract with both prompts
            original_extractions = await self._extract_all(
                original_prompt, test_documents, schema
            )

            edited_extractions = await self._extract_all(
                edited_prompt, test_documents, schema
            )

            # Compare results
            document_results = []
            original_target_correct = 0
            edited_target_correct = 0
            new_errors = []

            for i, doc in enumerate(test_documents):
                doc_id = doc.get("document_id", f"doc_{i}")
                verified_data = doc.get("verified_data", {})

                # Compare original extraction
                original_comparison = self._compare_extraction(
                    original_extractions[i], verified_data
                )

                # Compare edited extraction
                edited_comparison = self._compare_extraction(
                    edited_extractions[i], verified_data
                )

                # Check target field specifically
                target_original_match = original_comparison.get(target_field, {}).get(
                    "match", False
                )
                target_edited_match = edited_comparison.get(target_field, {}).get(
                    "match", False
                )

                if target_original_match:
                    original_target_correct += 1
                if target_edited_match:
                    edited_target_correct += 1

                # Detect new errors (fields that were correct but now wrong)
                doc_new_errors = self._detect_new_errors(
                    original_comparison, edited_comparison, target_field
                )

                if doc_new_errors:
                    new_errors.extend(
                        [{"document_id": doc_id, "field": err} for err in doc_new_errors]
                    )

                document_results.append(
                    {
                        "document_id": doc_id,
                        "target_field_fixed": not target_original_match
                        and target_edited_match,
                        "target_field_broken": target_original_match
                        and not target_edited_match,
                        "new_errors": doc_new_errors,
                        "original_accuracy": self._calculate_accuracy(
                            original_comparison
                        ),
                        "edited_accuracy": self._calculate_accuracy(edited_comparison),
                    }
                )

            # Calculate metrics
            total_docs = len(test_documents)
            original_target_accuracy = (
                original_target_correct / total_docs if total_docs > 0 else 0
            )
            edited_target_accuracy = (
                edited_target_correct / total_docs if total_docs > 0 else 0
            )
            target_field_improvement = (
                edited_target_accuracy - original_target_accuracy
            )

            # Calculate overall accuracy change
            original_overall = sum(
                r["original_accuracy"] for r in document_results
            ) / len(document_results)
            edited_overall = sum(r["edited_accuracy"] for r in document_results) / len(
                document_results
            )
            overall_accuracy_change = edited_overall - original_overall

            # Determine recommendation
            recommendation = self._make_recommendation(
                target_field_improvement,
                overall_accuracy_change,
                new_errors,
            )

            reasoning = self._build_reasoning(
                recommendation,
                target_field_improvement,
                overall_accuracy_change,
                new_errors,
            )

            logger.info(
                f"Dry run complete: {recommendation} "
                f"(target improvement: {target_field_improvement:+.1%})"
            )

            return {
                "recommendation": recommendation,
                "reasoning": reasoning,
                "target_field": target_field,
                "target_field_improvement": target_field_improvement,
                "original_target_accuracy": original_target_accuracy,
                "edited_target_accuracy": edited_target_accuracy,
                "overall_accuracy_change": overall_accuracy_change,
                "original_overall_accuracy": original_overall,
                "edited_overall_accuracy": edited_overall,
                "document_results": document_results,
                "new_errors": new_errors,
                "documents_tested": total_docs,
            }

        except Exception as e:
            logger.error(f"Dry run test failed: {e}")
            return {
                "error": str(e),
                "recommendation": "REJECT",
                "reasoning": f"Dry run testing failed: {str(e)}",
            }

    async def _extract_all(
        self,
        prompt: str,
        test_documents: List[Dict[str, Any]],
        schema: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Extract data from all test documents.

        Args:
            prompt: Extraction prompt to use
            test_documents: List of test documents
            schema: JSON schema

        Returns:
            List of extracted data dictionaries
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

                results.append(extraction_result["extracted_data"])

            except Exception as e:
                logger.error(
                    f"Extraction failed for document {doc.get('document_id')}: {e}"
                )
                results.append({})

        return results

    def _compare_extraction(
        self, extracted_data: Dict[str, Any], verified_data: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Compare extracted data with verified data field by field.

        Args:
            extracted_data: Data extracted by the prompt
            verified_data: Known correct data

        Returns:
            Dictionary mapping field paths to comparison results
        """
        # Flatten both dictionaries
        extracted_flat = self._flatten_dict(extracted_data)
        verified_flat = self._flatten_dict(verified_data)

        # Get all unique field paths
        all_fields = set(extracted_flat.keys()) | set(verified_flat.keys())

        results = {}
        for field_path in all_fields:
            extracted_value = extracted_flat.get(field_path)
            verified_value = verified_flat.get(field_path)

            # Normalize and compare
            extracted_norm = self._normalize_value(extracted_value)
            verified_norm = self._normalize_value(verified_value)

            match = extracted_norm == verified_norm

            results[field_path] = {
                "match": match,
                "extracted": extracted_value,
                "verified": verified_value,
            }

        return results

    def _flatten_dict(
        self, data: Dict[str, Any], parent_key: str = "", sep: str = "."
    ) -> Dict[str, Any]:
        """Flatten nested dictionary to dot notation.

        Args:
            data: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for key parts

        Returns:
            Flattened dictionary
        """
        items = []

        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.extend(
                            self._flatten_dict(item, f"{new_key}[{i}]", sep=sep).items()
                        )
                    else:
                        items.append((f"{new_key}[{i}]", item))
            else:
                items.append((new_key, v))

        return dict(items)

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

        return str(value)

    def _detect_new_errors(
        self,
        original_comparison: Dict[str, Dict],
        edited_comparison: Dict[str, Dict],
        target_field: str,
    ) -> List[str]:
        """Detect fields that were correct but became incorrect.

        Args:
            original_comparison: Comparison results with original prompt
            edited_comparison: Comparison results with edited prompt
            target_field: The field being tuned (exclude from new errors)

        Returns:
            List of field paths that regressed
        """
        new_errors = []

        for field_path in original_comparison.keys():
            # Skip the target field (that's what we're fixing)
            if field_path == target_field:
                continue

            original_match = original_comparison[field_path].get("match", False)
            edited_match = edited_comparison.get(field_path, {}).get("match", False)

            # If it was correct but now wrong, that's a new error
            if original_match and not edited_match:
                new_errors.append(field_path)

        return new_errors

    def _calculate_accuracy(self, comparison: Dict[str, Dict]) -> float:
        """Calculate accuracy from comparison results.

        Args:
            comparison: Field-by-field comparison results

        Returns:
            Accuracy as a float (0.0 to 1.0)
        """
        if not comparison:
            return 0.0

        total = len(comparison)
        correct = sum(1 for result in comparison.values() if result.get("match", False))

        return correct / total if total > 0 else 0.0

    def _make_recommendation(
        self,
        target_improvement: float,
        overall_change: float,
        new_errors: List[Dict],
    ) -> str:
        """Make ACCEPT/REJECT recommendation based on test results.

        Args:
            target_improvement: Accuracy improvement on target field
            overall_change: Overall accuracy change
            new_errors: List of new errors introduced

        Returns:
            "ACCEPT" or "REJECT"
        """
        # REJECT if new errors introduced
        if new_errors:
            return "REJECT"

        # REJECT if target field didn't improve enough
        if target_improvement < self.MIN_IMPROVEMENT_THRESHOLD:
            return "REJECT"

        # REJECT if overall accuracy decreased
        if overall_change < -0.05:  # Allow small decreases
            return "REJECT"

        return "ACCEPT"

    def _build_reasoning(
        self,
        recommendation: str,
        target_improvement: float,
        overall_change: float,
        new_errors: List[Dict],
    ) -> str:
        """Build human-readable reasoning for the recommendation.

        Args:
            recommendation: ACCEPT or REJECT
            target_improvement: Target field improvement
            overall_change: Overall accuracy change
            new_errors: New errors introduced

        Returns:
            Reasoning string
        """
        lines = []

        if recommendation == "ACCEPT":
            lines.append("ACCEPTED: Edit shows positive improvement")
            lines.append(
                f"Target field improved by {target_improvement:+.1%}"
            )
            lines.append(
                f"Overall accuracy changed by {overall_change:+.1%}"
            )
            lines.append("No new errors introduced")
        else:
            lines.append("REJECTED: Edit does not meet acceptance criteria")

            if target_improvement < self.MIN_IMPROVEMENT_THRESHOLD:
                lines.append(
                    f"Target field improvement ({target_improvement:+.1%}) "
                    f"below threshold ({self.MIN_IMPROVEMENT_THRESHOLD:.1%})"
                )

            if overall_change < -0.05:
                lines.append(
                    f"Overall accuracy decreased significantly ({overall_change:+.1%})"
                )

            if new_errors:
                lines.append(f"New errors introduced on {len(new_errors)} field(s):")
                for err in new_errors[:3]:  # Show first 3
                    lines.append(f"  - {err['field']} (doc: {err['document_id']})")
                if len(new_errors) > 3:
                    lines.append(f"  ... and {len(new_errors) - 3} more")

        return "\n".join(lines)

    def explain_results(self, test_result: Dict[str, Any]) -> str:
        """Generate a human-readable explanation of dry run results.

        Args:
            test_result: Test result dictionary from test_edit()

        Returns:
            Human-readable explanation string
        """
        if test_result.get("error"):
            return f"Dry Run Error: {test_result['error']}"

        recommendation = test_result.get("recommendation", "UNKNOWN")
        reasoning = test_result.get("reasoning", "No reasoning provided")

        explanation = f"""Dry Run Test Result: {recommendation}

{reasoning}

Target Field: {test_result.get('target_field')}
Target Field Accuracy: {test_result.get('original_target_accuracy', 0):.1%} → {test_result.get('edited_target_accuracy', 0):.1%}
Overall Accuracy: {test_result.get('original_overall_accuracy', 0):.1%} → {test_result.get('edited_overall_accuracy', 0):.1%}

Documents Tested: {test_result.get('documents_tested', 0)}
"""

        return explanation
