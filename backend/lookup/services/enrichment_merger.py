"""Enrichment Merger implementation for combining multiple Look-Up results.

This module provides functionality to merge enrichment data from multiple
Look-Up executions with confidence-based conflict resolution.
"""

from typing import Any


class EnrichmentMerger:
    """Merges enrichments from multiple Look-Ups with conflict resolution.

    When multiple Look-Ups run on the same input data, they may produce
    overlapping enrichment fields. This class handles merging those results
    and resolving conflicts based on confidence scores.
    """

    def merge(self, enrichments: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge enrichments with conflict resolution.

        Combines enrichment data from multiple Look-Up executions,
        resolving conflicts based on confidence scores when the same
        field appears in multiple enrichments.

        Args:
            enrichments: List of dicts with structure:
                {
                    'project_id': UUID,
                    'project_name': str,
                    'data': Dict[str, Any],  # Enrichment fields
                    'confidence': Optional[float],  # 0.0-1.0
                    'execution_time_ms': int,
                    'cached': bool
                }

        Returns:
            Dictionary containing:
                - data: Merged enrichment data
                - conflicts_resolved: Number of conflicts resolved
                - enrichment_details: Per-lookup metadata

        Example:
            >>> merger = EnrichmentMerger()
            >>> enrichments = [
            ...     {
            ...         "project_id": uuid1,
            ...         "project_name": "Vendor Matcher",
            ...         "data": {"vendor": "Slack", "category": "SaaS"},
            ...         "confidence": 0.95,
            ...         "execution_time_ms": 1234,
            ...         "cached": False,
            ...     },
            ...     {
            ...         "project_id": uuid2,
            ...         "project_name": "Product Classifier",
            ...         "data": {"category": "Communication", "type": "Software"},
            ...         "confidence": 0.80,
            ...         "execution_time_ms": 567,
            ...         "cached": True,
            ...     },
            ... ]
            >>> result = merger.merge(enrichments)
            >>> print(result["data"])
            {'vendor': 'Slack', 'category': 'SaaS', 'type': 'Software'}
            >>> print(result["conflicts_resolved"])
            1
        """
        merged_data = {}
        field_sources = {}  # Track which lookup contributed each field
        conflicts_resolved = 0
        enrichment_details = []

        # Process each enrichment
        for enrichment in enrichments:
            project_id = enrichment.get("project_id")
            project_name = enrichment.get("project_name", "Unknown")
            data = enrichment.get("data", {})
            confidence = enrichment.get("confidence")
            execution_time_ms = enrichment.get("execution_time_ms", 0)
            cached = enrichment.get("cached", False)

            fields_added = []

            # Process each field in the enrichment
            for field_name, field_value in data.items():
                field_entry = {
                    "lookup_id": project_id,
                    "lookup_name": project_name,
                    "confidence": confidence,
                    "value": field_value,
                }

                if field_name not in field_sources:
                    # No conflict, add the field
                    field_sources[field_name] = field_entry
                    merged_data[field_name] = field_value
                    fields_added.append(field_name)
                else:
                    # Conflict! Resolve it
                    existing = field_sources[field_name]
                    winner = self._resolve_conflict(field_name, existing, field_entry)

                    # Check if resolution changed the winner
                    if winner["lookup_id"] != existing["lookup_id"]:
                        # New winner, update the merged data
                        field_sources[field_name] = winner
                        merged_data[field_name] = winner["value"]
                        fields_added.append(field_name)
                        conflicts_resolved += 1
                    elif winner["lookup_id"] == field_entry["lookup_id"]:
                        # Current enrichment won but was not originally there
                        conflicts_resolved += 1

            # Track enrichment details
            enrichment_details.append(
                {
                    "lookup_project_id": str(project_id) if project_id else None,
                    "lookup_project_name": project_name,
                    "confidence": confidence,
                    "cached": cached,
                    "execution_time_ms": execution_time_ms,
                    "fields_added": fields_added,
                }
            )

        return {
            "data": merged_data,
            "conflicts_resolved": conflicts_resolved,
            "enrichment_details": enrichment_details,
        }

    def _resolve_conflict(self, field_name: str, existing: dict, new: dict) -> dict:
        """Resolve conflict for a single field.

        Uses confidence scores to determine which value to keep.
        When confidence scores are equal or absent, uses first-complete-wins
        strategy (keeps the existing value).

        Args:
            field_name: Name of the field with conflict (for context)
            existing: Dict with {lookup_id, lookup_name, confidence, value}
            new: Dict with {lookup_id, lookup_name, confidence, value}

        Returns:
            Winner dict with same structure

        Resolution rules:
            1. Both have confidence: higher confidence wins
            2. Equal confidence: first-complete wins (existing)
            3. One has confidence: confidence one wins
            4. Neither has confidence: first-complete wins (existing)
        """
        existing_confidence = existing.get("confidence")
        new_confidence = new.get("confidence")

        # Case 1: Both have confidence scores
        if existing_confidence is not None and new_confidence is not None:
            if new_confidence > existing_confidence:
                return new
            else:
                # Equal or existing is higher: keep existing (first-complete-wins)
                return existing

        # Case 2: Only new has confidence
        elif existing_confidence is None and new_confidence is not None:
            return new

        # Case 3: Only existing has confidence
        elif existing_confidence is not None and new_confidence is None:
            return existing

        # Case 4: Neither has confidence - first-complete-wins
        else:
            return existing
