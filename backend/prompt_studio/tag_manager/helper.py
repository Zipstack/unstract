import logging

from django.db import transaction
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_version_manager.models import PromptVersionManager
from prompt_studio.tag_manager.models import TagManager, TagManagerHelper
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class TagHelper:
    """Helper class for Custom tool operations."""

    @staticmethod
    def create_tag(tool_id: str, tag: str) -> Response:
        try:
            with transaction.atomic():
                tool = CustomTool.objects.get(pk=tool_id)
                tag_manager, created = TagManager.objects.get_or_create(
                    tool=tool,
                    tag=tag,
                )
                if created:
                    TagHelper._create_tag_manager_helper_entries(tag_manager)
                    tool.tag_id = tag_manager.id
                    tool.save()
                    message = "TagManager entry created successfully"
                    status_code = status.HTTP_201_CREATED
                    logger.info(message)
                else:
                    message = f"TagManager with tag '{tag}' already exists"
                    status_code = status.HTTP_409_CONFLICT
                    logger.error(message)

        except CustomTool.DoesNotExist:
            message = f"Prompt with id '{tool_id}' does not exist"
            status_code = status.HTTP_404_NOT_FOUND
            logger.error(message)

        except Exception as e:
            message = f"Error occurred during create_or_update_tag: {e}"
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            logger.error(message)

        return Response(
            data=message,
            status=status_code,
        )

    @staticmethod
    def _create_tag_manager_helper_entries(tag_manager):
        try:
            prompt_instances = PromptStudioHelper.fetch_prompt_from_tool(
                tool_id=tag_manager.tool_id, include_notes=True
            )
            tag_manager_helper_list = []
            for prompt_instance in prompt_instances:
                tag_manager_helper = TagManagerHelper(
                    tag_manager=tag_manager,
                    prompt_id=prompt_instance,
                    sequence_number=prompt_instance.sequence_number,
                    prompt_type=prompt_instance.prompt_type,
                    version=prompt_instance.loaded_version,
                )
                tag_manager_helper_list.append(tag_manager_helper)

            TagManagerHelper.objects.bulk_create(
                tag_manager_helper_list,
                update_conflicts=True,
                update_fields=["sequence_number", "prompt_type", "version"],
                unique_fields=["id", "prompt_id"],
            )
        except Exception as e:
            logger.error("Something went wrong: %s", e)
            raise e

    @staticmethod
    def load_tag(tool_id: str, tag: str) -> Response:
        try:
            with transaction.atomic():
                # Fetch all prompt instances for the given
                # tool_id without filtering by checked_in
                prompt_instances = PromptStudioHelper.fetch_prompt_from_tool(
                    tool_id=tool_id, checked_in_only=False
                )

                # Retrieve the TagManager and the corresponding
                # TagManagerHelper entries
                tag_manager = TagManager.objects.get(tool__tool_id=tool_id, tag=tag)
                tag_manager_helper_list = TagManagerHelper.objects.filter(
                    tag_manager=tag_manager
                )

                # Create a dictionary of prompt instances for quick lookup
                prompt_dict = {prompt.pk: prompt for prompt in prompt_instances}

                # First, set checked_in to False for all prompt instances
                for prompt_instance in prompt_instances:
                    prompt_instance.checked_in = False

                # Set checked_in to True for matched instances and update other fields
                for tag_manager_helper in tag_manager_helper_list:
                    prompt_instance = prompt_dict.get(tag_manager_helper.prompt_id.pk)

                    if prompt_instance:
                        prompt_version = tag_manager_helper.version
                        prompt_version_manager = PromptVersionManager.objects.get(
                            prompt_id=prompt_instance,
                            version=prompt_version,
                        )
                        prompt_instance.profile_manager = (
                            prompt_version_manager.profile_manager
                        )
                        prompt_instance.prompt_key = prompt_version_manager.prompt_key
                        prompt_instance.prompt = prompt_version_manager.prompt
                        prompt_instance.enforce_type = (
                            prompt_version_manager.enforce_type
                        )
                        prompt_instance.sequence_number = (
                            tag_manager_helper.sequence_number
                        )
                        prompt_instance.loaded_version = prompt_version
                        prompt_instance.checked_in = (
                            True  # Set checked_in to True for matched instances
                        )

                # Bulk update the modified prompt instances
                ToolStudioPrompt.objects.bulk_update(
                    prompt_dict.values(),
                    [
                        "profile_manager",
                        "prompt_key",
                        "prompt",
                        "enforce_type",
                        "sequence_number",
                        "loaded_version",
                        "checked_in",
                    ],
                )
                # Relace with helper from main
                tool = CustomTool.objects.get(pk=tool_id)
                tool.tag_id = tag_manager.id
                tool.save()
                logger.info("Updated prompt_instances with prompt from Tag Manager")
                return Response(
                    {
                        "message": "Prompt instances updated with "
                        f"prompt_version '{tag}'"
                    },
                    status=status.HTTP_200_OK,
                )

        except ToolStudioPrompt.DoesNotExist:
            logger.error("Prompt with tool_id %s does not exist.", tool_id)
            raise ValueError(f"Prompt with tool_id {tool_id} does not exist.")

        except TagManager.DoesNotExist:
            logger.error(
                "TagManager with tool_id %s and tag %s does not exist.", tool_id, tag
            )
            raise ValueError(
                f"TagManager with tool_id {tool_id} and tag {tag} does not exist."
            )

        except TagManagerHelper.DoesNotExist:
            logger.error(
                "No TagManagerHelper entries found for "
                "TagManager with tool_id %s and tag %s.",
                tool_id,
                tag,
            )
            raise ValueError(
                "No TagManagerHelper entries found for TagManager "
                f"with tool_id {tool_id} and tag {tag}."
            )

        except Exception as e:
            logger.error("Error occurred: %s", e)
            raise e
