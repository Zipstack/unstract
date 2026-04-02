"""LookupPromptTemplate model for managing prompt templates."""

import re
import uuid

from account_v2.models import User
from django.core.exceptions import ValidationError
from django.db import models
from utils.models.base_model import BaseModel


class LookupPromptTemplate(BaseModel):
    """Represents a prompt template with variable detection and validation.

    Each Look-Up project has one template that defines how to construct
    the LLM prompt with {{variable}} placeholders.
    """

    VARIABLE_PATTERN = r"\{\{([^}]+)\}\}"
    RESERVED_PREFIXES = ["_", "_lookup_"]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.OneToOneField(
        "lookup.LookupProject",
        on_delete=models.CASCADE,
        related_name="prompt_template_link",
        help_text="Parent Look-Up project",
    )

    # Template Configuration
    name = models.CharField(max_length=255, help_text="Template name for identification")
    template_text = models.TextField(help_text="Template with {{variable}} placeholders")
    llm_config = models.JSONField(
        default=dict, blank=True, help_text="LLM configuration including adapter_id"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this template is active"
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.RESTRICT,
        related_name="created_lookup_templates",
        help_text="User who created this template",
    )
    variable_mappings = models.JSONField(
        default=dict, blank=True, help_text="Optional documentation of variable mappings"
    )

    class Meta:
        """Model metadata."""

        db_table = "lookup_prompt_templates"
        ordering = ["-modified_at"]
        verbose_name = "Look-Up Prompt Template"
        verbose_name_plural = "Look-Up Prompt Templates"

    def __str__(self) -> str:
        """String representation."""
        return f"Template for {self.project.name}"

    def detect_variables(self) -> list[str]:
        """Detect all {{variable}} references in the template.

        Returns:
            List of unique variable paths found in the template.

        Example:
            Template: "Match {{input_data.vendor}} from {{reference_data}}"
            Returns: ["input_data.vendor", "reference_data"]
        """
        if not self.template_text:
            return []

        matches = re.findall(self.VARIABLE_PATTERN, self.template_text)
        # Strip whitespace and deduplicate
        unique_vars = list({m.strip() for m in matches})
        return sorted(unique_vars)

    def validate_syntax(self) -> bool:
        """Validate template syntax for matching braces.

        Returns:
            True if syntax is valid, False otherwise.

        Raises:
            ValidationError: If syntax is invalid.
        """
        # Check for unmatched opening braces
        open_count = self.template_text.count("{{")
        close_count = self.template_text.count("}}")

        if open_count != close_count:
            raise ValidationError(
                f"Mismatched braces in template: {open_count} opening, "
                f"{close_count} closing"
            )

        # Check for nested braces (not allowed)
        if re.search(r"\{\{[^}]*\{\{", self.template_text):
            raise ValidationError("Nested variable placeholders are not allowed")

        return True

    def validate_reserved_keywords(self) -> bool:
        """Check that template doesn't use reserved keywords.

        Returns:
            True if no reserved keywords are used.

        Raises:
            ValidationError: If reserved keywords are found.
        """
        variables = self.detect_variables()

        for var in variables:
            # Check if variable starts with reserved prefixes
            for prefix in self.RESERVED_PREFIXES:
                if var.startswith(prefix):
                    raise ValidationError(
                        f"Variable '{var}' uses reserved prefix '{prefix}'. "
                        f"Reserved prefixes: {', '.join(self.RESERVED_PREFIXES)}"
                    )

            # Check if trying to write to reserved fields
            if "=" in var or var.endswith("_metadata"):
                raise ValidationError(
                    f"Variable '{var}' appears to be trying to set a value. "
                    f"Variables should only reference existing data."
                )

        return True

    def get_variable_info(self) -> dict:
        """Get detailed information about detected variables.

        Returns:
            Dictionary with variable paths and their types/documentation.
        """
        variables = self.detect_variables()
        info = {}

        for var in variables:
            parts = var.split(".")
            if len(parts) > 0:
                root = parts[0]
                path = ".".join(parts[1:]) if len(parts) > 1 else ""

                info[var] = {
                    "root": root,
                    "path": path,
                    "depth": len(parts),
                    "description": self.variable_mappings.get(var, "No description"),
                }

        return info

    def clean(self):
        """Validate the template on save."""
        super().clean()

        if not self.template_text:
            raise ValidationError("Template text cannot be empty")

        try:
            self.validate_syntax()
            self.validate_reserved_keywords()
        except ValidationError as e:
            raise e

        # Warn if no variables detected (might be intentional)
        if not self.detect_variables():
            # This is just a warning, not an error
            pass

    @property
    def variable_count(self) -> int:
        """Get the count of unique variables in the template."""
        return len(self.detect_variables())
