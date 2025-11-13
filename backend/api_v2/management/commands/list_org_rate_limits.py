from django.core.management.base import BaseCommand

from api_v2.models import OrganizationRateLimit
from api_v2.rate_limiter import APIDeploymentRateLimiter


class Command(BaseCommand):
    help = "List all organization rate limits"

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-usage",
            action="store_true",
            help="Include current usage statistics (slower)",
        )

    def handle(self, *args, **options):
        with_usage = options["with_usage"]

        org_limits = OrganizationRateLimit.objects.select_related("organization").all()

        if not org_limits:
            self.stdout.write("No custom rate limits configured")
            return

        self.stdout.write(f"Found {org_limits.count()} custom rate limits:\n")

        for org_limit in org_limits:
            org = org_limit.organization
            limit = org_limit.concurrent_request_limit

            self.stdout.write(f"• {org.name} ({org.organization_id})")
            self.stdout.write(f"  Limit: {limit}")

            if with_usage:
                try:
                    usage = APIDeploymentRateLimiter.get_current_usage(org)
                    pct = (usage["org_count"] / limit * 100) if limit > 0 else 0
                    self.stdout.write(
                        f'  Usage: {usage["org_count"]}/{limit} ({pct:.1f}%)'
                    )
                except Exception as e:
                    self.stdout.write(f"  Usage: Error - {e}")

            self.stdout.write("")
