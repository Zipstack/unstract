"""Management command to fix AgenticProject records missing organization."""

from django.core.management.base import BaseCommand
from django.db import transaction

from account_v2.models import Organization
from prompt_studio.agentic_studio_v2.models import AgenticProject


class Command(BaseCommand):
    help = "Fix AgenticProject records that are missing organization field"

    def add_arguments(self, parser):
        parser.add_argument(
            "--org-id",
            type=str,
            help="Organization ID to assign to projects without organization",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, *args, **options):
        org_id = options.get("org_id")
        dry_run = options.get("dry_run", False)

        # Find projects without organization
        projects_without_org = AgenticProject.objects.filter(organization__isnull=True)
        count = projects_without_org.count()

        if count == 0:
            self.stdout.write(
                self.style.SUCCESS("No projects found without organization")
            )
            return

        self.stdout.write(
            self.style.WARNING(f"Found {count} projects without organization:")
        )

        # Display the projects
        for project in projects_without_org:
            self.stdout.write(
                f"  - {project.name} (ID: {project.id}, Created by: {project.created_by})"
            )

        # If no org_id provided, try to use the organization from created_by
        if not org_id:
            self.stdout.write(
                "\nNo organization ID provided. Will use organization from created_by user."
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n[DRY RUN] Would update the above projects")
            )
            return

        # Update projects
        with transaction.atomic():
            updated_count = 0
            for project in projects_without_org:
                if org_id:
                    # Use provided org_id
                    try:
                        org = Organization.objects.get(organization_id=org_id)
                        project.organization = org
                        project.save()
                        updated_count += 1
                        self.stdout.write(
                            f"  ✓ Updated {project.name} with org {org.organization_id}"
                        )
                    except Organization.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(
                                f"  ✗ Organization {org_id} not found. Skipping."
                            )
                        )
                        break
                elif project.created_by and hasattr(project.created_by, "organization"):
                    # Use organization from created_by user
                    project.organization = project.created_by.organization
                    project.save()
                    updated_count += 1
                    self.stdout.write(
                        f"  ✓ Updated {project.name} with org from creator"
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  - Skipped {project.name} (no org in user or no user)"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(f"\nSuccessfully updated {updated_count} projects")
        )
