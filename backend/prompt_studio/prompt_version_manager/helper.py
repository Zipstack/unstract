import logging

from django.db import transaction
from django.db.utils import IntegrityError
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_version_manager.models import PromptVersionManager
from rest_framework import status
from rest_framework.response import Response

logger = logging.getLogger(__name__)


class PromptVersionHelper:
    """Helper class for Custom tool operations."""

    @staticmethod
    def create_prompt_version(prompt_instances) -> None:
        for prompt_instance in prompt_instances:
            try:
                with transaction.atomic():
                    prompt_version_manager, created = (
                        PromptVersionManager.objects.get_or_create(
                            prompt_id=prompt_instance,
                            prompt_key=prompt_instance.prompt_key,
                            prompt=prompt_instance.prompt,
                            enforce_type=prompt_instance.enforce_type,
                            profile_manager=prompt_instance.profile_manager,
                        )
                    )
                    if created:
                        logger.info("Prompt version created successfully.")
                    else:
                        logger.info(
                            "Prompt version already exists with version: %s",
                            prompt_version_manager.version,
                        )
            except IntegrityError as e:
                logger.error("Integrity error occurred: %s", e)

    @staticmethod
    def get_prompt_version(prompt_instance) -> None:
        try:
            with transaction.atomic():
                prompt_version = PromptVersionManager.objects.get(
                    prompt_id=prompt_instance,
                    prompt_key=prompt_instance.prompt_key,
                    prompt=prompt_instance.prompt,
                    enforce_type=prompt_instance.enforce_type,
                    profile_manager=prompt_instance.profile_manager,
                ).version
                return prompt_version
        except PromptVersionManager.DoesNotExist:
            return PromptVersionManager.calculate_next_version(prompt_instance)

    @staticmethod
    def load_prompt_version(prompt_id, prompt_version) -> Response:
        try:
            with transaction.atomic():
                prompt_instance = ToolStudioPrompt.objects.get(pk=prompt_id)
                prompt_version_manager = PromptVersionManager.objects.get(
                    prompt_id=prompt_instance, version=prompt_version
                )
                # Check if the specified version is already loaded
                if prompt_version == prompt_instance.loaded_version:
                    message = (
                        f"Already loaded with version '{prompt_version}' "
                        f"for prompt_id '{prompt_id}'"
                    )
                    return Response(
                        {"message": message},
                        status=status.HTTP_200_OK,
                    )
                # Load specified version
                profile_manager = prompt_version_manager.profile_manager
                if profile_manager:
                    prompt_instance.profile_manager = profile_manager
                prompt_instance.prompt_key = prompt_version_manager.prompt_key
                prompt_instance.prompt = prompt_version_manager.prompt
                prompt_instance.enforce_type = prompt_version_manager.enforce_type
                prompt_instance.loaded_version = prompt_version
                prompt_instance.save()
                message = (
                    f"Loaded version '{prompt_version}' for prompt_id '{prompt_id}'"
                )
                logger.info(message)
                # Local import to avoid circular import
                from prompt_studio.prompt_studio.serializers import (
                    ToolStudioPromptSerializer,
                )

                return Response(
                    {
                        "message": message,
                        "loaded_data": ToolStudioPromptSerializer(prompt_instance).data,
                    },
                    status=status.HTTP_200_OK,
                )

        except ToolStudioPrompt.DoesNotExist:
            message = f"Prompt id '{prompt_id}' does not exist"
            logger.error(message)
            return Response({"error": message}, status=status.HTTP_404_NOT_FOUND)

        except PromptVersionManager.DoesNotExist:
            message = (
                f"Prompt version '{prompt_version}' does "
                f"not exist for prompt id '{prompt_id}'"
            )
            logger.error(message)
            return Response({"error": message}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            logger.error("Error occurred: %s", e)
            raise e
