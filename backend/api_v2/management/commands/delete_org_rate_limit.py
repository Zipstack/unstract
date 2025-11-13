from account_v2.models import Organization
from django.core.management.base import BaseCommand, CommandError

from api_v2.models import OrganizationRateLimit
from api_v2.rate_limiter import APIDeploymentRateLimiter


class Command(BaseCommand):
    help = "Delete custom organization rate limit (reverts to default)"

    def add_arguments(self, parser):
        parser.add_argument("org_id", type=str, help="Organization ID or name")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        org_id = options["org_id"]
        force = options["force"]

        # Get organization (try organization_id first, then name)
        try:
            organization = Organization.objects.get(organization_id=org_id)
        except Organization.DoesNotExist:
            try:
                organization = Organization.objects.get(name=org_id)
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{org_id}" not found')

        # Check if custom limit exists
        try:
            org_rate_limit = OrganizationRateLimit.objects.get(organization=organization)
        except OrganizationRateLimit.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    f'No custom rate limit found for organization "{organization.name}" '
                    f"({organization.organization_id})"
                )
            )
            return

        current_limit = org_rate_limit.concurrent_request_limit

        # Confirm deletion unless --force
        if not force:
            self.stdout.write(
                f"Organization: {organization.name} ({organization.organization_id})"
            )
            self.stdout.write(f"Current custom limit: {current_limit}")
            self.stdout.write(
                "\nThis will delete the custom rate limit and revert to the system default."
            )

            confirm = input("Continue? [y/N]: ")
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Cancelled"))
                return

        # Delete the custom limit (cache is automatically cleared via post_delete signal)
        org_rate_limit.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted custom rate limit for organization "{organization.name}" '
                f"({organization.organization_id})"
            )
        )

        # Show what default will be used
        from django.conf import settings

        from api_v2.rate_limit_constants import RateLimitDefaults

        default_limit = getattr(
            settings,
            "API_DEPLOYMENT_DEFAULT_RATE_LIMIT",
            RateLimitDefaults.DEFAULT_ORG_LIMIT,
        )
        self.stdout.write(
            self.style.WARNING(f"Will now use system default: {default_limit}")
        )

        # Show current usage
        try:
            usage = APIDeploymentRateLimiter.get_current_usage(organization)
            self.stdout.write(
                f'\nCurrent usage: {usage["org_count"]}/{default_limit} concurrent requests'
            )

            if usage["org_count"] >= default_limit:
                self.stdout.write(
                    self.style.ERROR(
                        "WARNING: Current usage exceeds default limit! "
                        "New requests will be rate limited until usage drops."
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not fetch current usage: {e}"))

        self.stdout.write(self.style.SUCCESS("✓ Cache automatically cleared"))
