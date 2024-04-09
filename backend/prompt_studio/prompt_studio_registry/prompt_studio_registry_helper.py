import logging
from typing import Any, Optional

from account.models import User
from django.conf import settings
from django.db import IntegrityError
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.prompt_studio_helper import (
    PromptStudioHelper,
)
from unstract.tool_registry.dto import Properties, Spec, Tool

from .constants import JsonSchemaKey
from .exceptions import InternalError, ToolSaveError
from .models import PromptStudioRegistry
from .serializers import PromptStudioRegistrySerializer

logger = logging.getLogger(__name__)


class PromptStudioRegistryHelper:
    """Class to register custom tools to tool studio registry.

    By default the exported tools will be private and will be executed
    with the help of a proto tool.
    """

    @staticmethod
    def frame_spec(tool: CustomTool) -> Spec:
        """Method to return spec of the Custom tool.

        Args:
            tool (CustomTool): Saved tool data

        Returns:
            dict: spec dict
        """
        spec = Spec(title=str(tool.tool_id), description=tool.description)
        return spec

    @staticmethod
    def frame_properties(tool: CustomTool) -> Properties:
        """Method to return properties of the tool.

        Args:
            tool (CustomTool): Saved custom tool data.

        Returns:
            dict: Properties dict
        """
        # TODO: Update for new architecture
        tool_props = Properties(
            display_name=tool.tool_name,
            function_name=str(tool.tool_id),
            description=tool.description,
        )
        return tool_props

    @staticmethod
    def get_tool_by_prompt_registry_id(
        prompt_registry_id: str,
    ) -> Optional[Tool]:
        """Gets the `Tool` associated with a prompt registry ID if it exists.

        Args:
            prompt_registry_id (str): Prompt registry ID to fetch for

        Returns:
            Optional[Tool]: The `Tool` exported from Prompt Studio
        """
        try:
            prompt_registry_tool = PromptStudioRegistry.objects.get(
                pk=prompt_registry_id
            )
        # Suppress all exceptions to allow processing
        except Exception as e:
            logger.warning(
                "Error while fetching for prompt registry "
                f"ID {prompt_registry_id}: {e} "
            )
            return None
        return Tool(
            tool_uid=prompt_registry_tool.prompt_registry_id,
            properties=Properties.from_dict(prompt_registry_tool.tool_property),
            spec=Spec.from_dict(prompt_registry_tool.tool_spec),
            icon=prompt_registry_tool.icon,
            image_url=settings.STRUCTURE_TOOL_IMAGE_URL,
            image_name=settings.STRUCTURE_TOOL_IMAGE_NAME,
            image_tag=settings.STRUCTURE_TOOL_IMAGE_TAG,
        )

    @staticmethod
    def update_or_create_psr_tool(
        custom_tool: CustomTool, shared_with_org: bool, user_ids: set[int]
    ) -> PromptStudioRegistry:
        """Updates or creates the PromptStudioRegistry record.

        This appears as a separate tool in the workflow and is mapped
        1:1 with the `CustomTool`.

        Args:
            tool_id (str): ID of the custom tool.

        Raises:
            ToolSaveError
            InternalError

        Returns:
            obj: PromptStudioRegistry instance that was updated or created
        """
        try:
            properties: Properties = (
                PromptStudioRegistryHelper.frame_properties(tool=custom_tool)
            )
            spec: Spec = PromptStudioRegistryHelper.frame_spec(tool=custom_tool)
            prompts: list[ToolStudioPrompt] = (
                PromptStudioHelper.fetch_prompt_from_tool(
                    tool_id=custom_tool.tool_id
                )
            )
            metadata = PromptStudioRegistryHelper.frame_export_json(
                tool=custom_tool, prompts=prompts
            )

            obj: PromptStudioRegistry
            created: bool
            obj, created = PromptStudioRegistry.objects.update_or_create(
                custom_tool=custom_tool,
                created_by=custom_tool.created_by,
                modified_by=custom_tool.modified_by,
                defaults={
                    "name": custom_tool.tool_name,
                    "tool_property": properties.to_dict(),
                    "tool_spec": spec.to_dict(),
                    "tool_metadata": metadata,
                    "icon": custom_tool.icon,
                    "description": custom_tool.description,
                },
            )
            if created:
                logger.info(f"PSR {obj.prompt_registry_id} was created")
            else:
                logger.info(f"PSR {obj.prompt_registry_id} was updated")
            obj.shared_to_org = shared_with_org
            obj.shared_users.clear()
            obj.shared_users.add(*user_ids)
            obj.save()
            return obj
        except IntegrityError as error:
            logger.error(
                "Integrity Error - Error occurred while "
                f"exporting custom tool : {error}"
            )
            raise ToolSaveError

    @staticmethod
    def frame_export_json(
        tool: CustomTool, prompts: list[ToolStudioPrompt]
    ) -> dict[str, Any]:
        export_metadata = {}

        prompt_grammer = tool.prompt_grammer
        grammar_list = []
        grammer_dict = {}
        outputs: list[dict[str, Any]] = []
        output: dict[str, Any] = {}
        if prompt_grammer:
            for word, synonyms in prompt_grammer.items():
                synonyms = prompt_grammer[word]
                grammer_dict[JsonSchemaKey.WORD] = word
                grammer_dict[JsonSchemaKey.SYNONYMS] = synonyms
                grammar_list.append(grammer_dict)
                grammer_dict = {}

        export_metadata[JsonSchemaKey.NAME] = tool.tool_name
        export_metadata[JsonSchemaKey.DESCRIPTION] = tool.description
        export_metadata[JsonSchemaKey.AUTHOR] = tool.author
        export_metadata[JsonSchemaKey.TOOL_ID] = str(tool.tool_id)

        vector_db = ""
        embedding_suffix = ""
        adapter_id = ""
        llm = ""
        embedding_model = ""

        default_llm_profile = ProfileManager.get_default_llm_profile(tool)
        for prompt in prompts:
            if prompt.prompt_type == JsonSchemaKey.NOTES:
                continue
            if not prompt.profile_manager:
                prompt.profile_manager = default_llm_profile

            vector_db = str(prompt.profile_manager.vector_store.id)
            embedding_model = str(prompt.profile_manager.embedding_model.id)
            llm = str(prompt.profile_manager.llm.id)
            x2text = str(prompt.profile_manager.x2text.id)
            adapter_id = str(prompt.profile_manager.embedding_model.adapter_id)
            embedding_suffix = adapter_id.split("|")[0]

            output[JsonSchemaKey.ASSERTION_FAILURE_PROMPT] = (
                prompt.assertion_failure_prompt
            )
            output[JsonSchemaKey.ASSERT_PROMPT] = prompt.assert_prompt
            output[JsonSchemaKey.IS_ASSERT] = prompt.is_assert
            output[JsonSchemaKey.PROMPT] = prompt.prompt
            output[JsonSchemaKey.ACTIVE] = prompt.active
            output[JsonSchemaKey.CHUNK_SIZE] = prompt.profile_manager.chunk_size
            output[JsonSchemaKey.VECTOR_DB] = vector_db
            output[JsonSchemaKey.EMBEDDING] = embedding_model
            output[JsonSchemaKey.X2TEXT_ADAPTER] = x2text
            output[JsonSchemaKey.CHUNK_OVERLAP] = (
                prompt.profile_manager.chunk_overlap
            )
            output[JsonSchemaKey.LLM] = llm
            output[JsonSchemaKey.PREAMBLE] = tool.preamble
            output[JsonSchemaKey.POSTAMBLE] = tool.postamble
            output[JsonSchemaKey.GRAMMAR] = grammar_list
            output[JsonSchemaKey.TYPE] = prompt.enforce_type
            output[JsonSchemaKey.NAME] = prompt.prompt_key
            output[JsonSchemaKey.RETRIEVAL_STRATEGY] = (
                prompt.profile_manager.retrieval_strategy
            )
            output[JsonSchemaKey.SIMILARITY_TOP_K] = (
                prompt.profile_manager.similarity_top_k
            )
            output[JsonSchemaKey.SECTION] = prompt.profile_manager.section
            output[JsonSchemaKey.REINDEX] = prompt.profile_manager.reindex
            output[JsonSchemaKey.EMBEDDING_SUFFIX] = embedding_suffix
            outputs.append(output)
            output = {}
            vector_db = ""
            embedding_suffix = ""
            adapter_id = ""
            llm = ""
            embedding_model = ""

        export_metadata[JsonSchemaKey.OUTPUTS] = outputs
        return export_metadata

    @staticmethod
    def fetch_json_for_registry(user: User) -> list[dict[str, Any]]:
        try:
            # filter the Prompt studio registry based on the users and org flag
            prompt_studio_tools = PromptStudioRegistry.objects.list_tools(user)
            pi_serializer = PromptStudioRegistrySerializer(
                instance=prompt_studio_tools, many=True
            )
        except Exception as error:
            logger.error(
                f"Error occured while fetching tool for tool_id: {error}"
            )
            raise InternalError()
        tool_metadata: dict[str, Any] = {}
        tool_list = []
        for prompts in pi_serializer.data:
            tool_metadata[JsonSchemaKey.NAME] = prompts.get(JsonSchemaKey.NAME)
            tool_metadata[JsonSchemaKey.DESCRIPTION] = prompts.get(
                JsonSchemaKey.DESCRIPTION
            )
            tool_metadata[JsonSchemaKey.ICON] = prompts.get(JsonSchemaKey.ICON)
            tool_metadata[JsonSchemaKey.FUNCTION_NAME] = prompts.get(
                JsonSchemaKey.PROMPT_REGISTRY_ID
            )
            tool_list.append(tool_metadata)
            tool_metadata = {}
        return tool_list
