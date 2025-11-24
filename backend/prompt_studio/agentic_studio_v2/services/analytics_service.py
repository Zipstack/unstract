"""Analytics service for Agentic Studio.

Provides field-level accuracy tracking, error classification,
and analytics aggregation for the Analytics tab.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.db.models import Count, Q
from prompt_studio.agentic_studio_v2.models import (
    AgenticComparisonResult,
    AgenticDocument,
    AgenticProject,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for analytics queries and aggregations."""

    @staticmethod
    def infer_category(field_path: str) -> str:
        """Infer field category from path using keyword matching.

        Args:
            field_path: Field path like "customer.name" or "items[0].sku"

        Returns:
            Category: "Header", "LineItems", "Totals", or "Other"
        """
        path_lower = field_path.lower()

        # LineItems: Contains array indices or item-related keywords
        if "[" in field_path or any(
            keyword in path_lower
            for keyword in ["item", "line", "product", "sku", "quantity"]
        ):
            return "LineItems"

        # Totals: Contains financial/sum keywords
        if any(
            keyword in path_lower
            for keyword in ["total", "amount", "tax", "sum", "price", "cost"]
        ):
            return "Totals"

        # Header: Contains document header keywords
        if any(
            keyword in path_lower
            for keyword in [
                "customer",
                "invoice",
                "date",
                "address",
                "name",
                "number",
                "id",
            ]
        ):
            return "Header"

        return "Other"

    @staticmethod
    def get_summary(project_id: str) -> Dict[str, Any]:
        """Get analytics summary for a project.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with summary statistics
        """
        try:
            # Get all comparison results for project
            results = AgenticComparisonResult.objects.filter(project_id=project_id)

            total_docs = results.values("document").distinct().count()
            total_fields = results.count()
            matched_fields = results.filter(match=True).count()
            failed_fields = total_fields - matched_fields

            overall_accuracy = (
                (matched_fields / total_fields * 100) if total_fields > 0 else 0.0
            )

            return {
                "total_docs": total_docs,
                "total_fields": total_fields,
                "matched_fields": matched_fields,
                "failed_fields": failed_fields,
                "overall_accuracy": round(overall_accuracy, 2),
            }

        except Exception as e:
            logger.error(f"Failed to get analytics summary: {e}")
            return {
                "total_docs": 0,
                "total_fields": 0,
                "matched_fields": 0,
                "failed_fields": 0,
                "overall_accuracy": 0.0,
            }

    @staticmethod
    def get_top_mismatched_fields(
        project_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top mismatched fields sorted by accuracy.

        Args:
            project_id: UUID of the project
            limit: Maximum number of fields to return

        Returns:
            List of field statistics
        """
        try:
            # Get all comparison results
            results = AgenticComparisonResult.objects.filter(project_id=project_id)

            # Group by field_path and calculate stats
            field_stats = {}
            for result in results:
                field_path = result.field_path

                if field_path not in field_stats:
                    field_stats[field_path] = {
                        "field_path": field_path,
                        "total": 0,
                        "correct": 0,
                        "incorrect": 0,
                        "error_types": defaultdict(int),
                    }

                field_stats[field_path]["total"] += 1

                if result.match:
                    field_stats[field_path]["correct"] += 1
                else:
                    field_stats[field_path]["incorrect"] += 1
                    if result.error_type:
                        field_stats[field_path]["error_types"][result.error_type] += 1

            # Calculate accuracy and get most common error
            top_fields = []
            for field_path, stats in field_stats.items():
                if stats["incorrect"] > 0:  # Only include fields with errors
                    accuracy = (
                        (stats["correct"] / stats["total"]) * 100
                        if stats["total"] > 0
                        else 0.0
                    )

                    # Get most common error type
                    common_error = None
                    if stats["error_types"]:
                        common_error = max(
                            stats["error_types"].items(), key=lambda x: x[1]
                        )[0]

                    top_fields.append(
                        {
                            "field_path": field_path,
                            "accuracy": round(accuracy, 2),
                            "incorrect": stats["incorrect"],
                            "common_error": common_error,
                        }
                    )

            # Sort by accuracy (lowest first) and limit
            top_fields.sort(key=lambda x: x["accuracy"])
            return top_fields[:limit]

        except Exception as e:
            logger.error(f"Failed to get top mismatched fields: {e}")
            return []

    @staticmethod
    def get_category_breakdown(project_id: str) -> List[Dict[str, Any]]:
        """Get category breakdown with accuracy per category.

        Args:
            project_id: UUID of the project

        Returns:
            List of category statistics
        """
        try:
            results = AgenticComparisonResult.objects.filter(project_id=project_id)

            # Group by category
            category_stats = defaultdict(
                lambda: {"total_fields": 0, "matched_fields": 0}
            )

            for result in results:
                category = AnalyticsService.infer_category(result.field_path)
                category_stats[category]["total_fields"] += 1
                if result.match:
                    category_stats[category]["matched_fields"] += 1

            # Calculate average accuracy
            breakdown = []
            for category, stats in category_stats.items():
                avg_accuracy = (
                    (stats["matched_fields"] / stats["total_fields"]) * 100
                    if stats["total_fields"] > 0
                    else 0.0
                )

                breakdown.append(
                    {
                        "category": category,
                        "total_fields": stats["total_fields"],
                        "avg_accuracy": round(avg_accuracy, 2),
                    }
                )

            # Sort by category name for consistency
            breakdown.sort(key=lambda x: x["category"])
            return breakdown

        except Exception as e:
            logger.error(f"Failed to get category breakdown: {e}")
            return []

    @staticmethod
    def get_error_type_distribution(project_id: str) -> List[Dict[str, Any]]:
        """Get error type distribution.

        Args:
            project_id: UUID of the project

        Returns:
            List of error type counts
        """
        try:
            # Query for error type counts
            error_counts = (
                AgenticComparisonResult.objects.filter(
                    project_id=project_id, match=False
                )
                .exclude(error_type__isnull=True)
                .values("error_type")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            return [
                {"error_type": item["error_type"], "count": item["count"]}
                for item in error_counts
            ]

        except Exception as e:
            logger.error(f"Failed to get error type distribution: {e}")
            return []

    @staticmethod
    def get_field_detail(project_id: str, field_path: str) -> Dict[str, Any]:
        """Get detailed analytics for a specific field.

        Args:
            project_id: UUID of the project
            field_path: Field path to analyze

        Returns:
            Dict with field details and mismatches
        """
        try:
            # Get all comparison results for this field
            results = AgenticComparisonResult.objects.filter(
                project_id=project_id, field_path=field_path
            ).select_related("document")

            total = results.count()
            matched = results.filter(match=True).count()
            accuracy = (matched / total * 100) if total > 0 else 100.0

            # Get mismatches with document info
            mismatches = []
            for result in results.filter(match=False):
                mismatches.append(
                    {
                        "doc_name": result.document.original_filename,
                        "verified": result.normalized_verified or "",
                        "extracted": result.normalized_extracted or "",
                        "error_type": result.error_type,
                    }
                )

            return {
                "field_path": field_path,
                "accuracy": round(accuracy, 2),
                "mismatches": mismatches,
            }

        except Exception as e:
            logger.error(f"Failed to get field detail for {field_path}: {e}")
            return {"field_path": field_path, "accuracy": 100.0, "mismatches": []}

    @staticmethod
    def get_mismatch_matrix(project_id: str) -> Dict[str, Any]:
        """Get mismatch matrix data for heatmap visualization.

        Args:
            project_id: UUID of the project

        Returns:
            Dict with docs, fields, and data arrays
        """
        try:
            # Get all documents for this project
            documents = AgenticDocument.objects.filter(
                project_id=project_id
            ).values("id", "original_filename")

            docs = [
                {"id": str(doc["id"]), "name": doc["original_filename"]}
                for doc in documents
            ]

            # Get all unique field paths
            field_paths = (
                AgenticComparisonResult.objects.filter(project_id=project_id)
                .values_list("field_path", flat=True)
                .distinct()
                .order_by("field_path")
            )

            fields = [{"path": field_path} for field_path in field_paths]

            # Get all comparison results
            results = AgenticComparisonResult.objects.filter(
                project_id=project_id
            ).select_related("document")

            # Build data points
            data = []
            for result in results:
                # Determine status
                if result.match:
                    status = "match"
                elif result.error_type == "minor":
                    status = "partial"
                else:
                    status = "mismatch"

                data.append(
                    {
                        "doc_id": str(result.document.id),
                        "field_path": result.field_path,
                        "status": status,
                    }
                )

            return {"docs": docs, "fields": fields, "data": data}

        except Exception as e:
            logger.error(f"Failed to get mismatch matrix: {e}")
            return {"docs": [], "fields": [], "data": []}
