"""ComparisonService: Compares extracted data vs verified ground truth.

This service performs field-level comparison, normalizes values,
classifies error types, and calculates accuracy metrics.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from unstract.prompt_service.helpers.llm_bridge import UnstractAutogenBridge

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service for comparing extracted data against verified ground truth.

    This service:
    1. Flattens nested JSON to field paths
    2. Normalizes values for comparison
    3. Compares field-by-field
    4. Classifies error types using LLM
    5. Calculates accuracy metrics
    """

    def __init__(self, lightweight_llm: Optional[UnstractAutogenBridge] = None):
        """Initialize comparison service.

        Args:
            lightweight_llm: Optional LLM bridge for error classification
        """
        self.lightweight_llm = lightweight_llm
        logger.info("Initialized ComparisonService")

    async def compare_data(
        self,
        extracted_data: Dict[str, Any],
        verified_data: Dict[str, Any],
        document_id: Optional[str] = None,
        use_llm_classification: bool = True,
    ) -> Dict[str, Any]:
        """Compare extracted data vs verified ground truth.

        Args:
            extracted_data: Data extracted by LLM
            verified_data: Ground truth data
            document_id: Optional document ID for logging
            use_llm_classification: Whether to use LLM for error classification

        Returns:
            Dict with comparison results:
            {
                "document_id": str,
                "total_fields": int,
                "matched_fields": int,
                "accuracy": float,
                "field_results": [
                    {
                        "field_path": str,
                        "match": bool,
                        "extracted_value": Any,
                        "verified_value": Any,
                        "normalized_extracted": str,
                        "normalized_verified": str,
                        "error_type": str | None
                    }
                ],
                "error_distribution": {...}
            }
        """
        try:
            # Flatten both JSON objects to field paths
            extracted_flat = self._flatten_json(extracted_data)
            verified_flat = self._flatten_json(verified_data)

            # Get all unique field paths
            all_fields = set(extracted_flat.keys()) | set(verified_flat.keys())

            # Compare each field
            field_results = []
            matched = 0
            error_types = {}

            for field_path in sorted(all_fields):
                extracted_value = extracted_flat.get(field_path)
                verified_value = verified_flat.get(field_path)

                # Normalize values
                norm_extracted = self._normalize_value(extracted_value)
                norm_verified = self._normalize_value(verified_value)

                # Compare
                match = norm_extracted == norm_verified

                if match:
                    matched += 1
                    error_type = None
                else:
                    # Classify error type
                    if use_llm_classification and self.lightweight_llm:
                        error_type = await self._classify_error_with_llm(
                            field_path, extracted_value, verified_value
                        )
                    else:
                        error_type = self._classify_error_heuristic(
                            extracted_value, verified_value
                        )

                    # Track error distribution
                    if error_type:
                        error_types[error_type] = error_types.get(error_type, 0) + 1

                field_results.append(
                    {
                        "field_path": field_path,
                        "match": match,
                        "extracted_value": extracted_value,
                        "verified_value": verified_value,
                        "normalized_extracted": norm_extracted,
                        "normalized_verified": norm_verified,
                        "error_type": error_type,
                    }
                )

            total = len(all_fields)
            accuracy = (matched / total) if total > 0 else 0.0

            logger.info(
                f"Comparison for {document_id}: {matched}/{total} fields matched "
                f"({accuracy:.1%} accuracy)"
            )

            return {
                "document_id": document_id or "unknown",
                "total_fields": total,
                "matched_fields": matched,
                "failed_fields": total - matched,
                "accuracy": accuracy,
                "field_results": field_results,
                "error_distribution": error_types,
            }

        except Exception as e:
            logger.error(f"Comparison failed for {document_id}: {e}")
            raise

    def _flatten_json(
        self, data: Dict[str, Any], parent_key: str = "", separator: str = "."
    ) -> Dict[str, Any]:
        """Flatten nested JSON to dot-notation paths.

        Args:
            data: Nested JSON object
            parent_key: Parent key prefix
            separator: Path separator

        Returns:
            Flattened dict with dot-notation keys
        """
        items = []

        for key, value in data.items():
            new_key = f"{parent_key}{separator}{key}" if parent_key else key

            if isinstance(value, dict):
                # Recursively flatten nested objects
                items.extend(self._flatten_json(value, new_key, separator).items())
            elif isinstance(value, list):
                # Handle arrays
                for i, item in enumerate(value):
                    array_key = f"{new_key}[{i}]"
                    if isinstance(item, dict):
                        items.extend(
                            self._flatten_json(item, array_key, separator).items()
                        )
                    else:
                        items.append((array_key, item))
            else:
                items.append((new_key, value))

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

        # Convert to string
        str_value = str(value)

        # Lowercase
        str_value = str_value.lower()

        # Remove extra whitespace
        str_value = " ".join(str_value.split())

        # Remove common punctuation
        str_value = re.sub(r'[,;:"\']', "", str_value)

        # Normalize numbers (remove commas, currency symbols)
        str_value = re.sub(r"[$€£¥,]", "", str_value)

        # Normalize dates (try common formats)
        str_value = self._normalize_date(str_value)

        return str_value.strip()

    def _normalize_date(self, value: str) -> str:
        """Attempt to normalize date strings.

        Args:
            value: String that might be a date

        Returns:
            Normalized date string or original value
        """
        # Try common date formats
        date_formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%B %d, %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%d %b %Y",
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(value, fmt)
                # Return in ISO format
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return value

    def _classify_error_heuristic(
        self, extracted_value: Any, verified_value: Any
    ) -> str:
        """Classify error type using heuristics.

        Args:
            extracted_value: Value from extraction
            verified_value: Ground truth value

        Returns:
            Error type classification
        """
        # Both missing
        if extracted_value is None and verified_value is None:
            return "none"

        # Extracted missing
        if extracted_value is None:
            return "missing"

        # Verified missing (false positive)
        if verified_value is None:
            return "extra"

        ext_str = str(extracted_value)
        ver_str = str(verified_value)

        # Check for truncation
        if ext_str in ver_str or ver_str in ext_str:
            if len(ext_str) < len(ver_str):
                return "truncation"
            else:
                return "extra_content"

        # Check for format differences (numbers)
        try:
            ext_num = float(re.sub(r"[^\d.-]", "", ext_str))
            ver_num = float(re.sub(r"[^\d.-]", "", ver_str))
            if abs(ext_num - ver_num) < 0.01:  # Very close
                return "format"
        except (ValueError, re.error):
            pass

        # Check similarity (Levenshtein-like)
        similarity = self._calculate_similarity(ext_str, ver_str)

        if similarity > 0.8:
            return "minor"
        elif similarity > 0.5:
            return "moderate"
        else:
            return "major"

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple similarity ratio between two strings.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity ratio (0.0 to 1.0)
        """
        # Simple character overlap
        set1 = set(str1.lower())
        set2 = set(str2.lower())

        if not set1 and not set2:
            return 1.0

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    async def _classify_error_with_llm(
        self, field_path: str, extracted_value: Any, verified_value: Any
    ) -> str:
        """Classify error type using LLM.

        Args:
            field_path: Field path
            extracted_value: Extracted value
            verified_value: Verified value

        Returns:
            Error type classification
        """
        if not self.lightweight_llm:
            return self._classify_error_heuristic(extracted_value, verified_value)

        try:
            from autogen_core.models import UserMessage

            prompt = f"""Classify the extraction error for this field:

Field: {field_path}
Extracted: {extracted_value}
Verified (correct): {verified_value}

Error types:
- truncation: Extracted value is cut off/incomplete
- format: Different formatting (e.g., "1500" vs "$1,500.00")
- missing: Field was not extracted
- minor: Small difference (typo, extra space, etc.)
- major: Completely different values
- other: Other type of error

Respond with ONLY the error type, nothing else."""

            message = UserMessage(content=prompt, source="user")
            result = await self.lightweight_llm.create(
                messages=[message], temperature=0.0, max_tokens=20
            )

            error_type = result.content.strip().lower()

            # Validate it's a known type
            valid_types = [
                "truncation",
                "format",
                "missing",
                "minor",
                "major",
                "other",
            ]
            if error_type in valid_types:
                return error_type
            else:
                logger.warning(f"LLM returned invalid error type: {error_type}")
                return "other"

        except Exception as e:
            logger.error(f"LLM error classification failed: {e}")
            return self._classify_error_heuristic(extracted_value, verified_value)

    async def batch_compare(
        self,
        comparisons: List[Dict[str, Any]],
        use_llm_classification: bool = False,
    ) -> Dict[str, Any]:
        """Compare multiple documents in batch.

        Args:
            comparisons: List of dicts with 'document_id', 'extracted', 'verified'
            use_llm_classification: Whether to use LLM for error classification

        Returns:
            Dict with batch comparison results
        """
        results = []
        total_fields = 0
        total_matched = 0

        for comp in comparisons:
            doc_id = comp.get("document_id")
            extracted = comp.get("extracted", {})
            verified = comp.get("verified", {})

            try:
                result = await self.compare_data(
                    extracted_data=extracted,
                    verified_data=verified,
                    document_id=doc_id,
                    use_llm_classification=use_llm_classification,
                )

                results.append(result)
                total_fields += result["total_fields"]
                total_matched += result["matched_fields"]

            except Exception as e:
                logger.error(f"Batch comparison failed for {doc_id}: {e}")
                results.append(
                    {
                        "document_id": doc_id,
                        "error": str(e),
                    }
                )

        overall_accuracy = (total_matched / total_fields) if total_fields > 0 else 0.0

        logger.info(
            f"Batch comparison: {total_matched}/{total_fields} fields matched "
            f"({overall_accuracy:.1%} accuracy)"
        )

        return {
            "total_documents": len(comparisons),
            "total_fields": total_fields,
            "total_matched": total_matched,
            "overall_accuracy": overall_accuracy,
            "results": results,
        }

    def get_failing_fields(
        self, comparison_result: Dict[str, Any], min_failures: int = 1
    ) -> List[Dict[str, Any]]:
        """Get fields that failed comparison.

        Args:
            comparison_result: Result from compare_data()
            min_failures: Minimum number of failures to include

        Returns:
            List of failing field info
        """
        failing = []

        for field_result in comparison_result.get("field_results", []):
            if not field_result["match"]:
                failing.append(
                    {
                        "field_path": field_result["field_path"],
                        "extracted": field_result["extracted_value"],
                        "verified": field_result["verified_value"],
                        "error_type": field_result["error_type"],
                    }
                )

        return failing

    def calculate_field_accuracy(
        self, batch_results: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate per-field accuracy across multiple documents.

        Args:
            batch_results: List of comparison results from batch_compare

        Returns:
            Dict mapping field_path to accuracy stats
        """
        field_stats = {}

        for result in batch_results:
            for field_result in result.get("field_results", []):
                field_path = field_result["field_path"]

                if field_path not in field_stats:
                    field_stats[field_path] = {
                        "total": 0,
                        "matched": 0,
                        "failed": 0,
                        "error_types": {},
                    }

                field_stats[field_path]["total"] += 1

                if field_result["match"]:
                    field_stats[field_path]["matched"] += 1
                else:
                    field_stats[field_path]["failed"] += 1
                    error_type = field_result.get("error_type", "unknown")
                    field_stats[field_path]["error_types"][error_type] = (
                        field_stats[field_path]["error_types"].get(error_type, 0) + 1
                    )

        # Calculate accuracy percentages
        for field_path, stats in field_stats.items():
            stats["accuracy"] = (
                (stats["matched"] / stats["total"]) if stats["total"] > 0 else 0.0
            )

        return field_stats
