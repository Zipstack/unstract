from account_v2.models import Organization
from django.core.management.base import BaseCommand, CommandError

from api_v2.models import OrganizationRateLimit
from api_v2.rate_limiter import APIDeploymentRateLimiter


class Command(BaseCommand):
    help = "Set or update organization rate limit for API deployments"

    def add_arguments(self, parser):
        parser.add_argument(
            "org_id", type=str, help="Organization ID or organization name"
        )
        parser.add_argument(
            "limit", type=int, help="Concurrent request limit (positive integer)"
        )

    def handle(self, *args, **options):
        org_id = options["org_id"]
        limit = options["limit"]

        # Validate limit
        if limit <= 0:
            raise CommandError("Limit must be a positive integer")

        # Get organization (try organization_id first, then name)
        try:
            organization = Organization.objects.get(organization_id=org_id)
        except Organization.DoesNotExist:
            # Try by name
            try:
                organization = Organization.objects.get(name=org_id)
            except Organization.DoesNotExist:
                raise CommandError(
                    f'Organization with ID or name "{org_id}" does not exist'
                )

        # Create or update rate limit
        # Cache is automatically cleared via model.save()
        org_rate_limit, created = OrganizationRateLimit.objects.update_or_create(
            organization=organization, defaults={"concurrent_request_limit": limit}
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f'{action} rate limit for organization "{organization.name}" '
                f"({organization.organization_id}): {limit}"
            )
        )

        # Show current usage
        try:
            usage = APIDeploymentRateLimiter.get_current_usage(organization)
            self.stdout.write(
                self.style.WARNING(
                    f"Current usage: {usage['org_count']}/{limit} concurrent requests"
                )
            )

            if usage["org_count"] >= limit:
                self.stdout.write(
                    self.style.ERROR(
                        "WARNING: Current usage exceeds new limit! "
                        "New requests will be rate limited until usage drops."
                    )
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Could not fetch current usage: {e}"))

        self.stdout.write(self.style.SUCCESS("✓ Cache automatically cleared"))
