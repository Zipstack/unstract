"""Migration utilities for safely handling lazy migration from profile-based
to adapter-based summarization configuration.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

logger = logging.getLogger(__name__)


class SummarizeMigrationUtils:
    """Utility class for handling summarize LLM adapter migrations safely."""

    @staticmethod
    def migrate_tool_to_adapter_based(
        tool_instance, skip_if_migrated: bool = True
    ) -> bool:
        """Safely migrate a tool from profile-based to adapter-based summarization.

        Args:
            tool_instance: The CustomTool instance to migrate
            skip_if_migrated: Skip if already migrated (default: True)

        Returns:
            bool: True if migration was performed, False if skipped or failed
        """
        # Import here to avoid circular import with ProfileManager -> CustomTool -> migration_utils
        from prompt_studio.prompt_profile_manager_v2.models import ProfileManager

        # Skip if already migrated
        if skip_if_migrated and tool_instance.summarize_llm_adapter:
            logger.debug(
                f"Tool {tool_instance.tool_id} already migrated to adapter-based summarization, "
                f"skipping migration (created_by: {tool_instance.created_by.email if tool_instance.created_by else 'unknown'}, "
                f"org: {tool_instance.organization})"
            )
            return False

        # Check if there's a summarize profile before entering transaction
        try:
            summarize_profile = ProfileManager.objects.get(
                prompt_studio_tool=tool_instance, is_summarize_llm=True
            )
        except ObjectDoesNotExist:
            logger.info(
                f"No summarize profile found for tool {tool_instance.tool_id}, skipping migration"
            )
            return False

        try:
            with transaction.atomic():
                # Re-fetch the instance within transaction to ensure fresh data
                tool_instance.refresh_from_db()

                # Double-check migration status within transaction
                if skip_if_migrated and tool_instance.summarize_llm_adapter:
                    return False

                # Re-fetch the summarize profile with lock within transaction
                try:
                    summarize_profile = ProfileManager.objects.select_for_update().get(
                        prompt_studio_tool=tool_instance, is_summarize_llm=True
                    )
                except ObjectDoesNotExist:
                    logger.info(
                        f"No summarize profile found for tool {tool_instance.tool_id}, skipping migration"
                    )
                    return False

                # Check if profile has an LLM adapter
                if not summarize_profile.llm:
                    logger.warning(
                        f"Summarize profile for tool {tool_instance.tool_id} has no LLM adapter, skipping migration"
                    )
                    return False

                # Perform the migration
                tool_instance.summarize_llm_adapter = summarize_profile.llm
                tool_instance.save(update_fields=["summarize_llm_adapter"])

                # Clear any existing profile-based summarize setting after successful migration
                ProfileManager.objects.filter(prompt_studio_tool=tool_instance).update(
                    is_summarize_llm=False
                )

                logger.info(
                    f"Successfully migrated tool {tool_instance.tool_id} from profile-based to adapter-based summarization"
                )
                return True

        except Exception as e:
            logger.warning(
                f"Failed to migrate tool {tool_instance.tool_id}: {str(e)}\n"
                f"Continuing with the deprecated approach for now",
                exc_info=True,
            )
            return False
