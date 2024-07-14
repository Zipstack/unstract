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
    def load_prompt_version(prompt_id, prompt_version) -> None:
        try:
            with transaction.atomic():
                prompt_instance = ToolStudioPrompt.objects.get(pk=prompt_id)
                prompt_version_manager = PromptVersionManager.objects.get(
                    prompt_id=prompt_instance, version=prompt_version
                )
                # Check if the specified version is already loaded
                if prompt_version == prompt_instance.loaded_version:
                    return Response(
                        {
                            "message": "Already loaded with "
                            f"prompt_version '{prompt_version}'"
                        },
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
                logger.info(
                    "Loaded version %s for prompt_id %s", prompt_version, prompt_id
                )
                return Response(
                    {
                        "message": "Prompt instance updated with "
                        "prompt from PromptVersionManager"
                    },
                    status=status.HTTP_200_OK,
                )

        except ToolStudioPrompt.DoesNotExist:
            logger.error("Prompt with id %s does not exist.", prompt_id)
            raise ValueError(f"Prompt with id {prompt_id} does not exist.")

        except PromptVersionManager.DoesNotExist:
            logger.error(
                "Prompt version does not exist for prompt id %s, and version %s.",
                prompt_id,
                prompt_version,
            )
            raise ValueError(
                "Prompt version does not exist " "for the prompt and version."
            )

        except Exception as e:
            logger.error("Error occurred: %s", e)
            raise e
