"""Data comparison utilities for comparing extracted vs verified data.

Based on AutoPrompt's comparison.py implementation.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ComparisonService:
    """Service for comparing extracted and verified data."""

    @staticmethod
    def normalize_value(value: Any) -> Any:
        """Normalize a value for comparison.

        Applies:
        - Trim whitespace for strings
        - Case-fold (lowercase) for strings
        - Recursive normalization for dicts and lists

        Args:
            value: Value to normalize

        Returns:
            Normalized value
        """
        if value is None:
            return None
        elif isinstance(value, str):
            return value.strip().casefold()
        elif isinstance(value, dict):
            return {k: ComparisonService.normalize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [ComparisonService.normalize_value(item) for item in value]
        elif isinstance(value, (int, float, bool)):
            return value
        else:
            # For other types, convert to string and normalize
            return str(value).strip().casefold()

    @staticmethod
    def compare_values(extracted: Any, verified: Any) -> bool:
        """Compare two normalized values for equality.

        Args:
            extracted: Extracted value (already normalized)
            verified: Verified value (already normalized)

        Returns:
            True if values match, False otherwise
        """
        # Handle None cases
        if extracted is None and verified is None:
            return True
        if extracted is None or verified is None:
            return False

        # Handle dict comparison
        if isinstance(extracted, dict) and isinstance(verified, dict):
            if set(extracted.keys()) != set(verified.keys()):
                return False
            return all(ComparisonService.compare_values(extracted[k], verified[k]) for k in extracted.keys())

        # Handle list comparison (strict order)
        if isinstance(extracted, list) and isinstance(verified, list):
            if len(extracted) != len(verified):
                return False
            return all(ComparisonService.compare_values(e, v) for e, v in zip(extracted, verified))

        # Direct equality for primitives
        return extracted == verified

    @staticmethod
    def compare_extracted_to_verified(
        extracted_data: dict[str, Any],
        verified_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare extracted data to verified data and generate a detailed report.

        Args:
            extracted_data: Data extracted by LLM
            verified_data: User-verified golden truth data

        Returns:
            Comparison result with:
            - matches: Number of matching fields
            - mismatches: Number of mismatching fields
            - total_fields: Total number of fields compared
            - accuracy: Percentage accuracy (0-100)
            - field_results: Dict mapping field paths to comparison results
        """
        # Filter out _source_refs infrastructure field before comparison
        # This field is used for PDF highlighting but should not affect accuracy
        extracted_filtered = {k: v for k, v in extracted_data.items() if k != "_source_refs"}
        verified_filtered = {k: v for k, v in verified_data.items() if k != "_source_refs"}

        # Normalize both datasets
        normalized_extracted = ComparisonService.normalize_value(extracted_filtered)
        normalized_verified = ComparisonService.normalize_value(verified_filtered)

        # Track field-level results
        field_results = {}

        def compare_recursive(extracted: Any, verified: Any, path: str = "") -> tuple[int, int]:
            """Recursively compare fields and count matches/mismatches.

            Args:
                extracted: Extracted value (normalized)
                verified: Verified value (normalized)
                path: Current field path (dot-separated)

            Returns:
                Tuple of (matches, total_fields)
            """
            matches = 0
            total_fields = 0

            if isinstance(verified, dict):
                for key, verified_value in verified.items():
                    current_path = f"{path}.{key}" if path else key
                    extracted_value = extracted.get(key) if isinstance(extracted, dict) else None

                    if isinstance(verified_value, (dict, list)):
                        # Recurse into nested structures
                        sub_matches, sub_total = compare_recursive(
                            extracted_value if extracted_value is not None else {},
                            verified_value,
                            current_path,
                        )
                        matches += sub_matches
                        total_fields += sub_total
                    else:
                        # Leaf field - compare values
                        total_fields += 1
                        is_match = ComparisonService.compare_values(extracted_value, verified_value)
                        if is_match:
                            matches += 1

                        field_results[current_path] = {
                            "extracted": extracted_value,
                            "verified": verified_value,
                            "match": is_match,
                        }

            elif isinstance(verified, list):
                # For arrays, we need to check each element
                max_len = max(len(verified), len(extracted) if isinstance(extracted, list) else 0)
                for i in range(max_len):
                    current_path = f"{path}[{i}]"
                    verified_item = verified[i] if i < len(verified) else None
                    extracted_item = extracted[i] if isinstance(extracted, list) and i < len(extracted) else None

                    if isinstance(verified_item, (dict, list)):
                        # Recurse into nested structures
                        sub_matches, sub_total = compare_recursive(
                            extracted_item if extracted_item is not None else {},
                            verified_item,
                            current_path,
                        )
                        matches += sub_matches
                        total_fields += sub_total
                    else:
                        # Leaf field in array
                        total_fields += 1
                        is_match = ComparisonService.compare_values(extracted_item, verified_item)
                        if is_match:
                            matches += 1

                        field_results[current_path] = {
                            "extracted": extracted_item,
                            "verified": verified_item,
                            "match": is_match,
                        }
            else:
                # Single value comparison
                total_fields = 1
                is_match = ComparisonService.compare_values(extracted, verified)
                if is_match:
                    matches = 1

                field_results[path] = {
                    "extracted": extracted,
                    "verified": verified,
                    "match": is_match,
                }

            return matches, total_fields

        # Run comparison
        matches, total_fields = compare_recursive(normalized_extracted, normalized_verified)

        # Calculate accuracy
        accuracy = (matches / total_fields * 100) if total_fields > 0 else 0.0

        result = {
            "matches": matches,
            "mismatches": total_fields - matches,
            "total_fields": total_fields,
            "accuracy": round(accuracy, 2),
            "field_results": field_results,
        }

        logger.info(
            f"Comparison complete: {matches}/{total_fields} fields match "
            f"({result['accuracy']}% accuracy)"
        )

        return result
