"""
API Hub Usage Tracker for API Deployments.

This module handles usage tracking by writing to the existing verticals.subscription_usage table
when API calls come through API hub with subscription headers. Uses the same pattern as
doc-splitter-service for daily usage aggregation.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from django.db import connection
from account_usage.models import PageUsage

logger = logging.getLogger(__name__)


class APIHubUsageTracker:
    """Tracks API usage directly in API hub database for billing."""
    
    def __init__(self):
        """Initialize the usage tracker."""
        # Use the verticals schema for subscription usage
        self.api_hub_schema = "verticals"
    
    def extract_api_hub_headers_from_request(self, request_headers: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Extract specific API hub headers from request.headers dictionary.
        
        Args:
            request_headers: Django request.headers dictionary (case-insensitive)
            
        Returns:
            Dictionary of normalized API hub headers or None if no subscription found
        """
        if not request_headers:
            return None
        
        # API hub header names to extract (only required fields for billing)
        api_hub_header_names = [
            'X-Subscription-Id', 
            'X-Organization', 
            'X-Product-Id', 
            'X-Subscription-Name'
        ]
        
        normalized_headers = {}
        for header_name in api_hub_header_names:
            if header_name in request_headers:
                # Convert X-Subscription-Id to subscription-id format directly
                clean_name = header_name.replace("X-", "").lower()
                normalized_headers[clean_name] = str(request_headers[header_name])
        
        # Check if this looks like an API hub request
        if normalized_headers and "subscription-id" in normalized_headers:
            return normalized_headers
        
        return None
    
    def is_api_hub_request(self, api_hub_headers: Optional[Dict[str, str]]) -> bool:
        """
        Check if this request should be tracked for API hub billing.
        Only checks if valid API hub headers are present.
        
        Args:
            api_hub_headers: Headers extracted from API hub
            
        Returns:
            True if this is an API hub request that should be tracked
        """
        if not api_hub_headers:
            return False
        
        # Must have subscription information for billing
        required_headers = ["subscription-id", "organization"]
        return all(header in api_hub_headers for header in required_headers)
    
    def store_usage(
        self,
        file_execution_id: str,
        api_hub_headers: Dict[str, str],
        organization_id: Optional[str] = None,
    ) -> bool:
        """
        Store usage in existing verticals.subscription_usage table.
        
        Fetches actual page count from page_usage table using file_execution_id (run_id).
        Uses the same UPSERT pattern as doc-splitter-service for daily aggregation.
        
        Args:
            file_execution_id: File execution ID (equals run_id in page_usage table)
            api_hub_headers: Headers from API hub (subscription info)
            organization_id: Organization identifier
            
        Returns:
            True if usage was stored successfully
        """
        if not self.is_api_hub_request(api_hub_headers):
            return False
        
        try:
            # Get required fields from headers
            subscription_id = api_hub_headers.get("subscription-id")
            product_id = api_hub_headers.get("product-id") 
            name = api_hub_headers.get("subscription-name")
            # Use organization from headers, fallback to parameter
            org_id = api_hub_headers.get("organization") or organization_id
            
            if not all([subscription_id, product_id, name, org_id]):
                logger.warning(f"Incomplete API hub headers for file_execution {file_execution_id}: {api_hub_headers}")
                return False
            
            # Fetch actual page count from page_usage table using file_execution_id (run_id)
            try:
                # Use filter to leverage the organization_id index for better performance
                if org_id:
                    page_usage = PageUsage.objects.filter(
                        run_id=file_execution_id,
                        organization_id=org_id
                    ).first()
                else:
                    # Fallback to run_id only if no organization_id available
                    page_usage = PageUsage.objects.filter(
                        run_id=file_execution_id
                    ).first()
                
                if not page_usage:
                    logger.debug(f"No page usage found for run_id {file_execution_id}")
                    return True  # No pages to track, but don't fail the API
                
                page_count = page_usage.pages_processed
                
                if page_count <= 0:
                    logger.debug(f"Zero pages processed for run_id {file_execution_id}")
                    return True  # No pages to track
                    
            except Exception as e:
                logger.warning(f"Error querying page usage for run_id {file_execution_id}: {e}")
                return True  # Don't fail the API for usage tracking issues
            
            # Use current date for daily aggregation (same as doc-splitter pattern)
            added_at = datetime.now(timezone.utc).date()
            last_updated_at = datetime.now(timezone.utc)
            
            # Write to verticals.subscription_usage - same pattern as platform-service page_usage()
            query = f"""
                INSERT INTO "{self.api_hub_schema}".subscription_usage
                ("subscriptionId", "addedAt", name, "userId", "productId", "pageCountTotal", "lastUpdatedAt")
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("subscriptionId", "addedAt")
                DO UPDATE SET
                    "pageCountTotal" = "{self.api_hub_schema}".subscription_usage."pageCountTotal" + EXCLUDED."pageCountTotal",
                    "lastUpdatedAt" = EXCLUDED."lastUpdatedAt"
                RETURNING "subscriptionId", "addedAt", "pageCountTotal"
            """
            
            params = (
                subscription_id,
                added_at,
                name,
                org_id,
                product_id,
                page_count,
                last_updated_at,
            )
            
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                
                # Get the result to see what happened
                row = cursor.fetchone()
                if row:
                    final_page_count = row[2]  # pageCountTotal
                    logger.info(
                        f"API hub usage stored: subscription {subscription_id} "
                        f"for {added_at} with {page_count} pages. "
                        f"Total: {final_page_count}"
                    )
            
            return True
            
        except Exception as e:
            # Check if the error is due to table not existing
            error_str = str(e).lower()
            if any(indicator in error_str for indicator in [
                'relation "verticals.subscription_usage" does not exist',
                'relation does not exist',
                'table "subscription_usage" doesn\'t exist',
                'no such table',
                'table or view does not exist',
                'does not exist'
            ]):
                # Table doesn't exist - skip usage tracking
                logger.debug(f"API hub usage table not found: {e}")
                return True  # Return success since main API execution completed
            
            # Unexpected error - log it but don't fail the API
            logger.warning(f"Failed to store API hub usage: {e}")
            return True  # Don't fail the main API execution for usage tracking issues
    


# Singleton instance
api_hub_usage_tracker = APIHubUsageTracker()