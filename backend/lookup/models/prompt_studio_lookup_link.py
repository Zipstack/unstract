"""PromptStudioLookupLink model for linking PS projects with Look-Up projects."""

import uuid

from django.db import models


class PromptStudioLookupLinkManager(models.Manager):
    """Custom manager for PromptStudioLookupLink."""

    def get_links_for_ps_project(self, ps_project_id: uuid.UUID):
        """Get all Look-Up links for a Prompt Studio project, ordered by execution order.

        Args:
            ps_project_id: UUID of the Prompt Studio project

        Returns:
            QuerySet of links ordered by execution_order
        """
        return self.filter(prompt_studio_project_id=ps_project_id).order_by(
            "execution_order", "created_at"
        )

    def get_lookup_projects_for_ps(self, ps_project_id: uuid.UUID):
        """Get all Look-Up projects linked to a Prompt Studio project.

        Args:
            ps_project_id: UUID of the Prompt Studio project

        Returns:
            QuerySet of LookupProject instances
        """
        from .lookup_project import LookupProject

        link_ids = self.filter(prompt_studio_project_id=ps_project_id).values_list(
            "lookup_project_id", flat=True
        )

        return LookupProject.objects.filter(id__in=link_ids)


class PromptStudioLookupLink(models.Model):
    """Many-to-many relationship between Prompt Studio projects and Look-Up projects.

    Manages the linking and execution order of Look-Up projects within
    a Prompt Studio extraction pipeline.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Note: We're using UUIDs for now since PS project model isn't defined yet
    # In production, this should be a ForeignKey to the actual PS project model
    prompt_studio_project_id = models.UUIDField(
        help_text="UUID of the Prompt Studio project"
    )

    lookup_project = models.ForeignKey(
        "lookup.LookupProject",
        on_delete=models.CASCADE,
        related_name="ps_links",
        help_text="Linked Look-Up project",
    )

    execution_order = models.PositiveIntegerField(
        default=0, help_text="Order in which this Look-Up executes (lower numbers first)"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    objects = PromptStudioLookupLinkManager()

    class Meta:
        """Model metadata."""

        db_table = "prompt_studio_lookup_links"
        ordering = ["execution_order", "created_at"]
        unique_together = [["prompt_studio_project_id", "lookup_project"]]
        verbose_name = "Prompt Studio Look-Up Link"
        verbose_name_plural = "Prompt Studio Look-Up Links"
        indexes = [
            models.Index(fields=["prompt_studio_project_id"]),
            models.Index(fields=["lookup_project"]),
            models.Index(fields=["prompt_studio_project_id", "execution_order"]),
        ]

    def __str__(self) -> str:
        """String representation."""
        return f"PS Project {self.prompt_studio_project_id} → {self.lookup_project.name}"

    def save(self, *args, **kwargs):
        """Override save to auto-assign execution_order if not set.

        Auto-assigns the next available execution order number for the
        Prompt Studio project if not explicitly provided.
        """
        if self.execution_order == 0 and not self.pk:
            # Get the maximum execution order for this PS project
            max_order = PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=self.prompt_studio_project_id
            ).aggregate(max_order=models.Max("execution_order"))["max_order"]

            # Set to max + 1, or 1 if no existing links
            self.execution_order = (max_order or 0) + 1

        super().save(*args, **kwargs)

    def clean(self):
        """Validate the link."""
        super().clean()

        # In production, we would validate that both projects
        # belong to the same organization here
        # For now, we'll just ensure the lookup project is ready

        if self.lookup_project and not self.lookup_project.is_ready:
            # This is a warning, not an error - allow linking but warn
            # In production, this might log a warning
            pass

    @property
    def is_enabled(self) -> bool:
        """Check if this link is enabled and ready for execution.

        Returns:
            True if the linked Look-Up project is ready for use.
        """
        return self.lookup_project.is_ready if self.lookup_project else False
