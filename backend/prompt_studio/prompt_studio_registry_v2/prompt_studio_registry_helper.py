import logging
from typing import Any, Optional

from account_v2.models import User
from adapter_processor_v2.models import AdapterInstance
from django.conf import settings
from django.db import IntegrityError
from prompt_studio.modifier_loader import ModifierConfig
from prompt_studio.modifier_loader import load_plugins as load_modifier_plugins
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from unstract.tool_registry.dto import Properties, Spec, Tool

from .constants import JsonSchemaKey, PromptStudioRegistryKeys
from .exceptions import (
    EmptyToolExportError,
    InternalError,
    InValidCustomToolError,
    ToolSaveError,
)
from .models import PromptStudioRegistry
from .serializers import PromptStudioRegistrySerializer

logger = logging.getLogger(__name__)
modifier_plugins = load_modifier_plugins()


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
        properties = {
            "challenge_llm": {
                "type": "string",
                "title": "Challenge LLM",
                "adapterType": "LLM",
                "description": "LLM to use for challenge",
                "adapterIdKey": "challenge_llm_adapter_id",
            },
            "enable_challenge": {
                "type": "boolean",
                "title": "Enable challenge",
                "default": False,
                "description": "Enables Challenge",
            },
            "summarize_as_source": {
                "type": "boolean",
                "title": "Summarize and use summary as source",
                "default": False,
                "description": "Enables summary and use summarized content as source",
            },
            "single_pass_extraction_mode": {
                "type": "boolean",
                "title": "Enable Single pass extraction",
                "default": False,
                "description": "Enables single pass extraction",
            },
        }

        spec = Spec(
            title=str(tool.tool_id),
            description=tool.description,
            required=[JsonSchemaKey.CHALLENGE_LLM],
            properties=properties,
        )
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
            properties: Properties = PromptStudioRegistryHelper.frame_properties(
                tool=custom_tool
            )
            spec: Spec = PromptStudioRegistryHelper.frame_spec(tool=custom_tool)
            prompts: list[ToolStudioPrompt] = PromptStudioHelper.fetch_prompt_from_tool(
                tool_id=custom_tool.tool_id
            )
            metadata = PromptStudioRegistryHelper.frame_export_json(
                tool=custom_tool, prompts=prompts
            )

            obj: PromptStudioRegistry
            created: bool
            obj, created = PromptStudioRegistry.objects.update_or_create(
                custom_tool=custom_tool,
                created_by=custom_tool.created_by,
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
            obj.modified_by = custom_tool.modified_by
            obj.shared_to_org = shared_with_org
            if not shared_with_org:
                obj.shared_users.clear()
                obj.shared_users.add(*user_ids)
                # add prompt studio users
                # for shared_user in custom_tool.shared_users:
                obj.shared_users.add(
                    *custom_tool.shared_users.all().values_list("id", flat=True)
                )
                # add prompt studio owner
                obj.shared_users.add(custom_tool.created_by)
            else:
                obj.shared_users.clear()
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
        invalidated_prompts: list[str] = []
        invalidated_outputs: list[str] = []

        if not prompts:
            raise EmptyToolExportError()

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

        default_llm_profile = ProfileManager.get_default_llm_profile(tool)
        challenge_llm_instance: Optional[AdapterInstance] = tool.challenge_llm
        challenge_llm: Optional[str] = None
        # Using default profile manager llm if challenge_llm is None
        if challenge_llm_instance:
            challenge_llm = str(challenge_llm_instance.id)
        else:
            challenge_llm = str(default_llm_profile.llm.id)

        embedding_suffix = ""
        adapter_id = ""
        vector_db = str(default_llm_profile.vector_store.id)
        embedding_model = str(default_llm_profile.embedding_model.id)
        llm = str(default_llm_profile.llm.id)
        x2text = str(default_llm_profile.x2text.id)

        # Tool settings
        tool_settings = {}
        tool_settings[JsonSchemaKey.SUMMARIZE_PROMPT] = tool.summarize_prompt
        tool_settings[JsonSchemaKey.SUMMARIZE_AS_SOURCE] = tool.summarize_as_source
        tool_settings[JsonSchemaKey.PREAMBLE] = tool.preamble
        tool_settings[JsonSchemaKey.POSTAMBLE] = tool.postamble
        tool_settings[JsonSchemaKey.GRAMMAR] = grammar_list
        tool_settings[JsonSchemaKey.LLM] = llm
        tool_settings[JsonSchemaKey.X2TEXT_ADAPTER] = x2text
        tool_settings[JsonSchemaKey.VECTOR_DB] = vector_db
        tool_settings[JsonSchemaKey.EMBEDDING] = embedding_model
        tool_settings[JsonSchemaKey.CHUNK_SIZE] = default_llm_profile.chunk_size
        tool_settings[JsonSchemaKey.CHUNK_OVERLAP] = default_llm_profile.chunk_overlap
        tool_settings[JsonSchemaKey.ENABLE_CHALLENGE] = tool.enable_challenge
        tool_settings[JsonSchemaKey.CHALLENGE_LLM] = challenge_llm
        tool_settings[JsonSchemaKey.ENABLE_SINGLE_PASS_EXTRACTION] = (
            tool.single_pass_extraction_mode
        )
        tool_settings[JsonSchemaKey.ENABLE_HIGHLIGHT] = tool.enable_highlight
        tool_settings[JsonSchemaKey.PLATFORM_POSTAMBLE] = getattr(
            settings, JsonSchemaKey.PLATFORM_POSTAMBLE.upper(), ""
        )

        for prompt in prompts:
            if prompt.prompt_type == JsonSchemaKey.NOTES or not prompt.active:
                continue

            if not prompt.prompt:
                invalidated_prompts.append(prompt.prompt_key)
                continue

            prompt_output = PromptStudioOutputManager.objects.filter(
                tool_id=tool.tool_id,
                prompt_id=prompt.prompt_id,
                profile_manager=prompt.profile_manager,
            ).all()

            if not prompt_output:
                invalidated_outputs.append(prompt.prompt_key)
                continue

            if not prompt.profile_manager:
                prompt.profile_manager = default_llm_profile

            vector_db = str(prompt.profile_manager.vector_store.id)
            embedding_model = str(prompt.profile_manager.embedding_model.id)
            llm = str(prompt.profile_manager.llm.id)
            x2text = str(prompt.profile_manager.x2text.id)
            adapter_id = str(prompt.profile_manager.embedding_model.adapter_id)
            embedding_suffix = adapter_id.split("|")[0]

            output[JsonSchemaKey.PROMPT] = prompt.prompt
            output[JsonSchemaKey.ACTIVE] = prompt.active
            output[JsonSchemaKey.CHUNK_SIZE] = prompt.profile_manager.chunk_size
            output[JsonSchemaKey.VECTOR_DB] = vector_db
            output[JsonSchemaKey.EMBEDDING] = embedding_model
            output[JsonSchemaKey.X2TEXT_ADAPTER] = x2text
            output[JsonSchemaKey.CHUNK_OVERLAP] = prompt.profile_manager.chunk_overlap
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

            if (
                prompt.enforce_type == PromptStudioRegistryKeys.TABLE
                or prompt.enforce_type == PromptStudioRegistryKeys.RECORD
            ):
                for modifier_plugin in modifier_plugins:
                    cls = modifier_plugin[ModifierConfig.METADATA][
                        ModifierConfig.METADATA_SERVICE_CLASS
                    ]
                    output = cls.update(
                        output=output,
                        tool_id=tool.tool_id,
                        prompt_id=prompt.prompt_id,
                        prompt=prompt.prompt,
                    )

            outputs.append(output)
            output = {}
            vector_db = ""
            embedding_suffix = ""
            adapter_id = ""
            llm = ""
            embedding_model = ""

        if not outputs:
            raise EmptyToolExportError()

        if invalidated_prompts:
            raise InValidCustomToolError(
                f"Cannot export tool. Prompt(s): {', '.join(invalidated_prompts)} "
                "are empty. Please enter a valid prompt."
            )
        if invalidated_outputs:
            raise InValidCustomToolError(
                f"Cannot export tool. Prompt(s): {', '.join(invalidated_outputs)} "
                "were not run. Please run them before exporting."
            )
        export_metadata[JsonSchemaKey.TOOL_SETTINGS] = tool_settings
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
            logger.error(f"Error occured while fetching tool for tool_id: {error}")
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
