from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from account_v2.models import Organization
from api_v2.models import OrganizationRateLimit
from api_v2.rate_limit_constants import RateLimitKeys


class Command(BaseCommand):
    help = "View organization rate limit information and current usage"

    def add_arguments(self, parser):
        parser.add_argument(
            "org_id", type=str, help="Organization ID (UUID) or name"
        )
        parser.add_argument(
            "--clear-cache", action="store_true", help="Clear cache and force refresh from DB"
        )

    def handle(self, *args, **options):
        org_id = options["org_id"]
        clear_cache = options["clear_cache"]

        # Get organization
        try:
            from uuid import UUID

            UUID(org_id)
            organization = Organization.objects.get(organization_id=org_id)
        except (ValueError, Organization.DoesNotExist):
            try:
                organization = Organization.objects.get(name=org_id)
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{org_id}" not found')

        org_uuid = str(organization.organization_id)

        # Clear cache if requested
        if clear_cache:
            cache_key = RateLimitKeys.get_org_limit_cache_key(org_uuid)
            cache.delete(cache_key)
            self.stdout.write(self.style.WARNING("Cache cleared"))

        # Get from DB
        try:
            org_limit = OrganizationRateLimit.objects.get(organization=organization)
            db_limit = org_limit.concurrent_request_limit
            self.stdout.write(f"Database Limit: {db_limit}")
            self.stdout.write(f"Last Modified: {org_limit.modified_at}")
        except OrganizationRateLimit.DoesNotExist:
            self.stdout.write("Database Limit: Not set")
            db_limit = settings.API_DEPLOYMENT_DEFAULT_RATE_LIMIT
            self.stdout.write(f"Using Default: {db_limit}")

        # Check cache status
        cache_key = RateLimitKeys.get_org_limit_cache_key(org_uuid)
        cached_limit = cache.get(cache_key)
        if cached_limit is not None:
            self.stdout.write(f"Cached Limit: {cached_limit} ✓")
        else:
            self.stdout.write(
                "Cached Limit: Not cached (will be cached on next request)"
            )

        # Get current usage
        from api_v2.rate_limiter import APIDeploymentRateLimiter

        try:
            usage = APIDeploymentRateLimiter.get_current_usage(organization)

            self.stdout.write("\n--- Current Usage ---")
            self.stdout.write(
                f'Organization: {usage["org_count"]}/{usage["org_limit"]} concurrent requests'
            )
            self.stdout.write(
                f'Global System: {usage["global_count"]}/{usage["global_limit"]} concurrent requests'
            )

            # Usage percentage
            org_pct = (
                (usage["org_count"] / usage["org_limit"] * 100)
                if usage["org_limit"] > 0
                else 0
            )

            if org_pct >= 90:
                self.stdout.write(
                    self.style.ERROR(f"⚠ Organization at {org_pct:.1f}% capacity")
                )
            elif org_pct >= 70:
                self.stdout.write(
                    self.style.WARNING(f"Organization at {org_pct:.1f}% capacity")
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f"Organization at {org_pct:.1f}% capacity")
                )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error fetching usage: {e}"))
