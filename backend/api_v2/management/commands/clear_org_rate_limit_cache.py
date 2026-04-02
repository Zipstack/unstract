from account_v2.models import Organization
from django.core.cache import cache
from django.core.management.base import BaseCommand

from api_v2.models import OrganizationRateLimit
from api_v2.rate_limit_constants import RateLimitKeys


class Command(BaseCommand):
    help = (
        "Clear rate limit cache for organizations (useful after changing default limit)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=str,
            help="Clear cache for specific organization ID or name (default: all orgs)",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Clear cache for ALL organizations (with or without custom limits)",
        )

    def handle(self, *args, **options):
        org_id = options.get("org_id")
        clear_all = options["all"]

        if org_id:
            # Clear cache for specific organization
            self._clear_org_cache(org_id)
        elif clear_all:
            # Clear cache for ALL organizations
            self._clear_all_orgs_cache()
        else:
            # Clear cache for organizations with custom limits
            self._clear_custom_limits_cache()

    def _clear_org_cache(self, org_id: str):
        """Clear cache for a specific organization."""
        # Get organization
        try:
            organization = Organization.objects.get(organization_id=org_id)
        except Organization.DoesNotExist:
            try:
                organization = Organization.objects.get(name=org_id)
            except Organization.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Organization "{org_id}" not found'))
                return

        cache_key = RateLimitKeys.get_org_limit_cache_key(
            str(organization.organization_id)
        )
        cache.delete(cache_key)

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Cleared cache for {organization.name} ({organization.organization_id})"
            )
        )

    def _clear_custom_limits_cache(self):
        """Clear cache for organizations with custom rate limits."""
        org_limits = OrganizationRateLimit.objects.select_related("organization").all()

        if not org_limits:
            self.stdout.write(
                self.style.WARNING("No custom rate limits found - nothing to clear")
            )
            return

        count = 0
        for org_limit in org_limits:
            org_id = str(org_limit.organization.organization_id)
            cache_key = RateLimitKeys.get_org_limit_cache_key(org_id)
            cache.delete(cache_key)
            count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Cleared cache for {count} organizations with custom limits"
            )
        )

    def _clear_all_orgs_cache(self):
        """Clear cache for ALL organizations (with or without custom limits)."""
        self.stdout.write(
            self.style.WARNING(
                "Clearing cache for ALL organizations (including those using defaults)..."
            )
        )

        # Try pattern-based deletion first (works with Redis cache backend)
        if self._try_pattern_delete():
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ Cleared all organization rate limit caches using pattern deletion"
                )
            )
        else:
            # Fallback: iterate through all organizations
            self._clear_all_orgs_individually()

        self.stdout.write(
            self.style.WARNING(
                "Note: Cache will be repopulated on next API request for each org"
            )
        )

    def _try_pattern_delete(self) -> bool:
        """Try to delete cache keys using pattern (Redis-specific).

        Returns:
            True if pattern deletion succeeded, False if not supported
        """
        try:
            # Check if cache backend supports delete_pattern (Redis cache)
            if hasattr(cache, "delete_pattern"):
                pattern = RateLimitKeys.ORG_LIMIT_CACHE_KEY_PATTERN.replace(
                    "{org_id}", "*"
                )
                deleted_count = cache.delete_pattern(pattern)
                self.stdout.write(f"Deleted {deleted_count} cache keys using pattern")
                return True
            return False
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Pattern deletion failed: {e}"))
            return False

    def _clear_all_orgs_individually(self):
        """Fallback: Clear cache by iterating through all organizations."""
        organizations = Organization.objects.all()
        count = organizations.count()

        if count == 0:
            self.stdout.write(self.style.WARNING("No organizations found"))
            return

        # Confirm for large number of orgs
        if count > 50:
            self.stdout.write(
                f"This will clear cache for {count} organizations individually."
            )
            confirm = input("Continue? [y/N]: ")
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Cancelled"))
                return

        cleared = 0
        for org in organizations:
            cache_key = RateLimitKeys.get_org_limit_cache_key(str(org.organization_id))
            cache.delete(cache_key)
            cleared += 1

        self.stdout.write(
            self.style.SUCCESS(f"✓ Cleared cache for {cleared} organizations")
        )
