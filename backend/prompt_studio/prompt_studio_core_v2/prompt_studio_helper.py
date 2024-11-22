import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from account_v2.constants import Common
from account_v2.models import User
from adapter_processor_v2.constants import AdapterKeys
from adapter_processor_v2.models import AdapterInstance
from django.conf import settings
from django.db.models.manager import BaseManager
from file_management.file_management_helper import FileManagerHelper
from prompt_studio.modifier_loader import ModifierConfig
from prompt_studio.modifier_loader import load_plugins as load_modifier_plugins
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_profile_manager_v2.profile_manager_helper import (
    ProfileManagerHelper,
)
from prompt_studio.prompt_studio_core_v2.constants import IndexingStatus, LogLevels
from prompt_studio.prompt_studio_core_v2.constants import (
    ToolStudioPromptKeys as TSPKeys,
)
from prompt_studio.prompt_studio_core_v2.document_indexing_service import (
    DocumentIndexingService,
)
from prompt_studio.prompt_studio_core_v2.exceptions import (
    AnswerFetchError,
    DefaultProfileError,
    EmptyPromptError,
    IndexingAPIError,
    NoPromptsFound,
    OperationNotSupported,
    PermissionError,
    ToolNotValid,
)
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.prompt_ide_base_tool import PromptIdeBaseTool
from prompt_studio.prompt_studio_core_v2.prompt_variable_service import (
    PromptStudioVariableService,
)
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (  # noqa: E501
    PromptStudioIndexHelper,
)
from prompt_studio.prompt_studio_output_manager_v2.output_manager_helper import (
    OutputManagerHelper,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from unstract.sdk.constants import LogLevel
from unstract.sdk.exceptions import IndexingError, SdkError
from unstract.sdk.index import Index
from unstract.sdk.prompt import PromptTool
from unstract.sdk.utils.tool_utils import ToolUtils
from utils.local_context import StateStore

from unstract.core.pubsub_helper import LogPublisher

CHOICES_JSON = "/static/select_choices.json"
ERROR_MSG = "User %s doesn't have access to adapter %s"

logger = logging.getLogger(__name__)

modifier_plugins = load_modifier_plugins()


class PromptStudioHelper:
    """Helper class for Custom tool operations."""

    @staticmethod
    def create_default_profile_manager(user: User, tool_id: uuid) -> None:
        """Create a default profile manager for a given user and tool.

        Args:
            user (User): The user for whom the default profile manager is
            created.
            tool_id (uuid): The ID of the tool for which the default profile
            manager is created.

        Raises:
            AdapterInstance.DoesNotExist: If no suitable adapter instance is
            found for creating the default profile manager.

        Returns:
            None
        """
        try:
            AdapterInstance.objects.get(
                is_friction_less=True,
                is_usable=True,
                adapter_type=AdapterKeys.LLM,
            )

            default_adapters: BaseManager[AdapterInstance] = (
                AdapterInstance.objects.filter(is_friction_less=True)
            )

            profile_manager = ProfileManager(
                prompt_studio_tool=CustomTool.objects.get(pk=tool_id),
                is_default=True,
                created_by=user,
                modified_by=user,
                chunk_size=0,
                profile_name="sample profile",
                chunk_overlap=0,
                section="Default",
                retrieval_strategy="simple",
                similarity_top_k=3,
            )

            for adapter in default_adapters:
                if adapter.adapter_type == AdapterKeys.LLM:
                    profile_manager.llm = adapter
                elif adapter.adapter_type == AdapterKeys.VECTOR_DB:
                    profile_manager.vector_store = adapter
                elif adapter.adapter_type == AdapterKeys.X2TEXT:
                    profile_manager.x2text = adapter
                elif adapter.adapter_type == AdapterKeys.EMBEDDING:
                    profile_manager.embedding_model = adapter

            profile_manager.save()

        except AdapterInstance.DoesNotExist:
            logger.info("skipping default profile creation")

    @staticmethod
    def validate_adapter_status(
        profile_manager: ProfileManager,
    ) -> None:
        """Helper method to validate the status of adapters in profile manager.

        Args:
            profile_manager (ProfileManager): The profile manager instance to
              validate.

        Raises:
            PermissionError: If the owner does not have permission to perform
              the action.
        """

        error_msg = "Permission Error: Free usage for the configured trial adapter exhausted.Please connect your own service accounts to continue.Please see our documentation for more details:https://docs.unstract.com/unstract_platform/setup_accounts/whats_needed"  # noqa: E501
        adapters = [
            profile_manager.llm,
            profile_manager.vector_store,
            profile_manager.embedding_model,
            profile_manager.x2text,
        ]

        for adapter in adapters:
            if not adapter.is_usable:
                raise PermissionError(error_msg)

    @staticmethod
    def validate_profile_manager_owner_access(
        profile_manager: ProfileManager,
    ) -> None:
        """Helper method to validate the owner's access to the profile manager.

        Args:
            profile_manager (ProfileManager): The profile manager instance to
              validate.

        Raises:
            PermissionError: If the owner does not have permission to perform
              the action.
        """
        profile_manager_owner = profile_manager.created_by

        is_llm_owned = (
            profile_manager.llm.shared_to_org
            or profile_manager.llm.created_by == profile_manager_owner
            or profile_manager.llm.shared_users.filter(
                pk=profile_manager_owner.pk
            ).exists()
        )
        is_vector_store_owned = (
            profile_manager.vector_store.shared_to_org
            or profile_manager.vector_store.created_by == profile_manager_owner
            or profile_manager.vector_store.shared_users.filter(
                pk=profile_manager_owner.pk
            ).exists()
        )
        is_embedding_model_owned = (
            profile_manager.embedding_model.shared_to_org
            or profile_manager.embedding_model.created_by == profile_manager_owner
            or profile_manager.embedding_model.shared_users.filter(
                pk=profile_manager_owner.pk
            ).exists()
        )
        is_x2text_owned = (
            profile_manager.x2text.shared_to_org
            or profile_manager.x2text.created_by == profile_manager_owner
            or profile_manager.x2text.shared_users.filter(
                pk=profile_manager_owner.pk
            ).exists()
        )

        if not (
            is_llm_owned
            and is_vector_store_owned
            and is_embedding_model_owned
            and is_x2text_owned
        ):
            adapter_names = set()
            if not is_llm_owned:
                logger.error(
                    ERROR_MSG,
                    profile_manager_owner.user_id,
                    profile_manager.llm.id,
                )
                adapter_names.add(profile_manager.llm.adapter_name)
            if not is_vector_store_owned:
                logger.error(
                    ERROR_MSG,
                    profile_manager_owner.user_id,
                    profile_manager.vector_store.id,
                )
                adapter_names.add(profile_manager.vector_store.adapter_name)
            if not is_embedding_model_owned:
                logger.error(
                    ERROR_MSG,
                    profile_manager_owner.user_id,
                    profile_manager.embedding_model.id,
                )
                adapter_names.add(profile_manager.embedding_model.adapter_name)
            if not is_x2text_owned:
                logger.error(
                    ERROR_MSG,
                    profile_manager_owner.user_id,
                    profile_manager.x2text.id,
                )
                adapter_names.add(profile_manager.x2text.adapter_name)
            if len(adapter_names) > 1:
                error_msg = (
                    f"Multiple permission errors were encountered with {', '.join(adapter_names)}",  # noqa: E501
                )
            else:
                error_msg = (
                    f"Permission Error: You do not have access to {adapter_names.pop()}",  # noqa: E501
                )

            raise PermissionError(error_msg)

    @staticmethod
    def _publish_log(
        component: dict[str, str], level: str, state: str, message: str
    ) -> None:
        LogPublisher.publish(
            StateStore.get(Common.LOG_EVENTS_ID),
            LogPublisher.log_prompt(component, level, state, message),
        )

    @staticmethod
    def get_select_fields() -> dict[str, Any]:
        """Method to fetch dropdown field values for frontend.

        Returns:
            dict[str, Any]: Dict for dropdown data
        """
        f = open(f"{os.path.dirname(__file__)}{CHOICES_JSON}")
        choices = f.read()
        f.close()
        response: dict[str, Any] = json.loads(choices)
        for modifier_plugin in modifier_plugins:
            cls = modifier_plugin[ModifierConfig.METADATA][
                ModifierConfig.METADATA_SERVICE_CLASS
            ]
            response = cls.update_select_choices(default_choices=response)
        return response

    @staticmethod
    def _fetch_prompt_from_id(id: str) -> ToolStudioPrompt:
        """Internal function used to fetch prompt from ID.

        Args:
            id (_type_): UUID of the prompt

        Returns:
            ToolStudioPrompt: Instance of the model
        """
        prompt_instance: ToolStudioPrompt = ToolStudioPrompt.objects.get(pk=id)
        return prompt_instance

    @staticmethod
    def fetch_prompt_from_tool(tool_id: str) -> list[ToolStudioPrompt]:
        """Internal function used to fetch mapped prompts from ToolID.

        Args:
            tool_id (_type_): UUID of the tool

        Returns:
            List[ToolStudioPrompt]: List of instance of the model
        """
        prompt_instances: list[ToolStudioPrompt] = ToolStudioPrompt.objects.filter(
            tool_id=tool_id
        ).order_by(TSPKeys.SEQUENCE_NUMBER)
        return prompt_instances

    @staticmethod
    def index_document(
        tool_id: str,
        file_name: str,
        org_id: str,
        user_id: str,
        document_id: str,
        is_summary: bool = False,
        run_id: str = None,
        text_processor: Optional[type[Any]] = None,
    ) -> Any:
        """Method to index a document.

        Args:
            tool_id (str): Id of the tool
            file_name (str): File to parse
            org_id (str): The ID of the organization to which the user belongs.
            user_id (str): The ID of the user who uploaded the document.
            is_summary (bool, optional): Whether the document is a summary
                or not. Defaults to False.

        Raises:
            ToolNotValid
            IndexingError
        """
        tool: CustomTool = CustomTool.objects.get(pk=tool_id)
        if is_summary:
            profile_manager: ProfileManager = ProfileManager.objects.get(
                prompt_studio_tool=tool, is_summarize_llm=True
            )
            default_profile = profile_manager
            file_path = file_name
        else:
            default_profile = ProfileManager.get_default_llm_profile(tool)
            file_path = FileManagerHelper.handle_sub_directory_for_tenants(
                org_id,
                is_create=False,
                user_id=user_id,
                tool_id=tool_id,
            )
            file_path = str(Path(file_path) / file_name)

        if not tool:
            logger.error(f"No tool instance found for the ID {tool_id}")
            raise ToolNotValid()

        start_time = time.time()
        logger.info(f"[{tool_id}] Indexing started for doc: {file_name}")
        PromptStudioHelper._publish_log(
            {"tool_id": tool_id, "run_id": run_id, "doc_name": file_name},
            LogLevels.INFO,
            LogLevels.RUN,
            "Indexing started",
        )

        # Validate the status of adapter in profile manager
        PromptStudioHelper.validate_adapter_status(default_profile)
        # Need to check the user who created profile manager
        # has access to adapters configured in profile manager
        PromptStudioHelper.validate_profile_manager_owner_access(default_profile)
        process_text = None
        if text_processor:
            process_text = text_processor.process
        doc_id = PromptStudioHelper.dynamic_indexer(
            profile_manager=default_profile,
            tool_id=tool_id,
            file_path=file_path,
            org_id=org_id,
            document_id=document_id,
            is_summary=is_summary,
            reindex=True,
            run_id=run_id,
            user_id=user_id,
            process_text=process_text,
        )

        elapsed_time = time.time() - start_time
        logger.info(
            f"[{tool_id}] Indexing successful for doc: {file_name},"
            f" took {elapsed_time:.3f}s"
        )
        logger.info(f"[{tool_id}] Indexing successful for doc: {file_name}")
        PromptStudioHelper._publish_log(
            {"tool_id": tool_id, "run_id": run_id, "doc_name": file_name},
            LogLevels.INFO,
            LogLevels.RUN,
            f"Indexing successful, took {elapsed_time:.3f}s",
        )

        return doc_id.get("output")

    @staticmethod
    def prompt_responder(
        tool_id: str,
        org_id: str,
        user_id: str,
        document_id: str,
        id: Optional[str] = None,
        run_id: str = None,
        profile_manager_id: Optional[str] = None,
        text_processor: Optional[type[Any]] = None,
    ) -> Any:
        """Execute chain/single run of the prompts. Makes a call to prompt
        service and returns the dict of response.

        Args:
            tool_id (str): ID of tool created in prompt studio
            org_id (str): Organization ID
            user_id (str): User's ID
            document_id (str): UUID of the document uploaded
            id (Optional[str]): ID of the prompt
            profile_manager_id (Optional[str]): UUID of the profile manager

        Raises:
            AnswerFetchError: Error from prompt-service

        Returns:
            Any: Dictionary containing the response from prompt-service
        """
        document: DocumentManager = DocumentManager.objects.get(pk=document_id)
        doc_name: str = document.document_name
        doc_path = PromptStudioHelper._get_document_path(
            org_id, user_id, tool_id, doc_name
        )

        if id:
            return PromptStudioHelper._execute_single_prompt(
                id=id,
                doc_path=doc_path,
                doc_name=doc_name,
                tool_id=tool_id,
                org_id=org_id,
                user_id=user_id,
                document_id=document_id,
                run_id=run_id,
                profile_manager_id=profile_manager_id,
                text_processor=text_processor,
            )
        else:
            return PromptStudioHelper._execute_prompts_in_single_pass(
                doc_path=doc_path,
                doc_name=doc_name,
                tool_id=tool_id,
                org_id=org_id,
                user_id=user_id,
                document_id=document_id,
                run_id=run_id,
                text_processor=text_processor,
            )

    @staticmethod
    def _execute_single_prompt(
        id,
        doc_path,
        doc_name,
        tool_id,
        org_id,
        user_id,
        document_id,
        run_id,
        profile_manager_id,
        text_processor: Optional[type[Any]] = None,
    ):
        prompt_instance = PromptStudioHelper._fetch_prompt_from_id(id)

        if (
            prompt_instance.enforce_type == TSPKeys.TABLE
            or prompt_instance.enforce_type == TSPKeys.RECORD
        ) and not modifier_plugins:
            raise OperationNotSupported()

        prompt_name = prompt_instance.prompt_key
        PromptStudioHelper._publish_log(
            {
                "tool_id": tool_id,
                "run_id": run_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevels.INFO,
            LogLevels.RUN,
            "Executing single prompt",
        )
        prompts = [prompt_instance]
        tool = prompt_instance.tool_id

        if tool.summarize_as_source:
            directory, filename = os.path.split(doc_path)
            doc_path = os.path.join(
                directory, TSPKeys.SUMMARIZE, os.path.splitext(filename)[0] + ".txt"
            )

        PromptStudioHelper._publish_log(
            {
                "tool_id": tool_id,
                "run_id": run_id,
                "prompt_key": prompt_name,
                "doc_name": doc_name,
            },
            LogLevels.DEBUG,
            LogLevels.RUN,
            "Invoking prompt service",
        )
        process_text = None
        if text_processor:
            process_text = text_processor.process
        try:
            response = PromptStudioHelper._fetch_response(
                doc_path=doc_path,
                doc_name=doc_name,
                tool=tool,
                prompt=prompt_instance,
                org_id=org_id,
                document_id=document_id,
                run_id=run_id,
                profile_manager_id=profile_manager_id,
                user_id=user_id,
                process_text=process_text,
            )
            return PromptStudioHelper._handle_response(
                response=response,
                run_id=run_id,
                prompts=prompts,
                document_id=document_id,
                is_single_pass=False,
                profile_manager_id=profile_manager_id,
            )
        except Exception as e:
            logger.error(
                f"[{tool.tool_id}] Error while fetching response for "
                f"prompt {id} and doc {document_id}: {e}"
            )
            msg = str(e)
            PromptStudioHelper._publish_log(
                {
                    "tool_id": tool_id,
                    "run_id": run_id,
                    "prompt_key": prompt_name,
                    "doc_name": doc_name,
                },
                LogLevels.ERROR,
                LogLevels.RUN,
                msg,
            )
            raise e

    @staticmethod
    def _execute_prompts_in_single_pass(
        doc_path,
        doc_name,
        tool_id,
        org_id,
        user_id,
        document_id,
        run_id,
        text_processor: Optional[type[Any]] = None,
    ):
        prompts = PromptStudioHelper.fetch_prompt_from_tool(tool_id)
        prompts = [
            prompt
            for prompt in prompts
            if prompt.prompt_type != TSPKeys.NOTES
            and prompt.active
            and prompt.enforce_type != TSPKeys.TABLE
            and prompt.enforce_type != TSPKeys.RECORD
        ]
        if not prompts:
            logger.error(f"[{tool_id or 'NA'}] No prompts found for id: {id}")
            raise NoPromptsFound()

        PromptStudioHelper._publish_log(
            {"tool_id": tool_id, "run_id": run_id, "prompt_id": str(id)},
            LogLevels.INFO,
            LogLevels.RUN,
            "Executing prompts in single pass",
        )
        process_text = None
        if text_processor:
            process_text = text_processor.process
        try:
            tool = prompts[0].tool_id
            response = PromptStudioHelper._fetch_single_pass_response(
                file_path=doc_path,
                doc_name=doc_name,
                tool=tool,
                prompts=prompts,
                org_id=org_id,
                document_id=document_id,
                run_id=run_id,
                user_id=user_id,
                process_text=process_text,
            )
            return PromptStudioHelper._handle_response(
                response=response,
                run_id=run_id,
                prompts=prompts,
                document_id=document_id,
                is_single_pass=True,
            )
        except Exception as e:
            logger.error(
                f"[{tool.tool_id}] Error while fetching single pass response: {e}"
            )
            PromptStudioHelper._publish_log(
                {
                    "tool_id": tool_id,
                    "run_id": run_id,
                    "prompt_id": str(id),
                },
                LogLevels.ERROR,
                LogLevels.RUN,
                f"Failed to fetch single pass response. {e}",
            )
            raise e

    @staticmethod
    def _get_document_path(org_id, user_id, tool_id, doc_name):
        doc_path = FileManagerHelper.handle_sub_directory_for_tenants(
            org_id=org_id,
            user_id=user_id,
            tool_id=tool_id,
            is_create=False,
        )
        return str(Path(doc_path) / doc_name)

    @staticmethod
    def _get_extract_or_summary_document_path(
        org_id, user_id, tool_id, doc_name, doc_type
    ) -> str:
        doc_path = FileManagerHelper.handle_sub_directory_for_tenants(
            org_id=org_id,
            user_id=user_id,
            tool_id=tool_id,
            is_create=False,
        )
        extracted_doc_name = Path(doc_name).stem + TSPKeys.TXT_EXTENTION
        return str(Path(doc_path) / doc_type / extracted_doc_name)

    @staticmethod
    def _handle_response(
        response,
        run_id,
        prompts,
        document_id,
        is_single_pass,
        profile_manager_id=None,
    ):
        if response.get("status") == IndexingStatus.PENDING_STATUS.value:
            return {
                "status": IndexingStatus.PENDING_STATUS.value,
                "message": IndexingStatus.DOCUMENT_BEING_INDEXED.value,
            }

        return OutputManagerHelper.handle_prompt_output_update(
            run_id=run_id,
            prompts=prompts,
            outputs=response["output"],
            document_id=document_id,
            is_single_pass_extract=is_single_pass,
            profile_manager_id=profile_manager_id,
            metadata=response["metadata"],
        )

    @staticmethod
    def _fetch_response(
        tool: CustomTool,
        doc_path: str,
        doc_name: str,
        prompt: ToolStudioPrompt,
        org_id: str,
        document_id: str,
        run_id: str,
        user_id: str,
        profile_manager_id: Optional[str] = None,
        process_text: Optional[Callable[[str], str]] = None,
    ) -> Any:
        """Utility function to invoke prompt service. Used internally.

        Args:
            tool (CustomTool): CustomTool instance (prompt studio project)
            doc_path (str): Path to the document
            doc_name (str): Name of the document
            prompt (ToolStudioPrompt): ToolStudioPrompt instance to fetch response
            org_id (str): UUID of the organization
            document_id (str): UUID of the document
            profile_manager_id (Optional[str]): UUID of the profile manager
            user_id (str): The ID of the user who uploaded the document


        Raises:
            DefaultProfileError: If no default profile is selected
            AnswerFetchError: Due to failures in prompt service

        Returns:
            Any: Output from LLM
        """

        # Fetch the ProfileManager instance using the profile_manager_id if provided
        profile_manager = prompt.profile_manager
        if profile_manager_id:
            profile_manager = ProfileManagerHelper.get_profile_manager(
                profile_manager_id=profile_manager_id
            )

        monitor_llm_instance: Optional[AdapterInstance] = tool.monitor_llm
        monitor_llm: Optional[str] = None
        challenge_llm_instance: Optional[AdapterInstance] = tool.challenge_llm
        challenge_llm: Optional[str] = None

        if monitor_llm_instance:
            monitor_llm = str(monitor_llm_instance.id)
        else:
            # Using default profile manager llm if monitor_llm is None
            default_profile = ProfileManager.get_default_llm_profile(tool)
            monitor_llm = str(default_profile.llm.id)

        # Using default profile manager llm if challenge_llm is None
        if challenge_llm_instance:
            challenge_llm = str(challenge_llm_instance.id)
        else:
            default_profile = ProfileManager.get_default_llm_profile(tool)
            challenge_llm = str(default_profile.llm.id)

        # Need to check the user who created profile manager
        PromptStudioHelper.validate_adapter_status(profile_manager)
        # Need to check the user who created profile manager
        # has access to adapters
        PromptStudioHelper.validate_profile_manager_owner_access(profile_manager)
        # Not checking reindex here as there might be
        # change in Profile Manager
        vector_db = str(profile_manager.vector_store.id)
        embedding_model = str(profile_manager.embedding_model.id)
        llm = str(profile_manager.llm.id)
        x2text = str(profile_manager.x2text.id)
        if not profile_manager:
            raise DefaultProfileError()
        index_result = PromptStudioHelper.dynamic_indexer(
            profile_manager=profile_manager,
            file_path=doc_path,
            tool_id=str(tool.tool_id),
            org_id=org_id,
            document_id=document_id,
            is_summary=tool.summarize_as_source,
            run_id=run_id,
            user_id=user_id,
            process_text=process_text,
        )
        if index_result.get("status") == IndexingStatus.PENDING_STATUS.value:
            return {
                "status": IndexingStatus.PENDING_STATUS.value,
                "message": IndexingStatus.DOCUMENT_BEING_INDEXED.value,
            }
        tool_id = str(tool.tool_id)
        output: dict[str, Any] = {}
        outputs: list[dict[str, Any]] = []
        grammer_dict = {}
        grammar_list = []
        # Adding validations
        prompt_grammer = tool.prompt_grammer
        if prompt_grammer:
            for word, synonyms in prompt_grammer.items():
                synonyms = prompt_grammer[word]
                grammer_dict[TSPKeys.WORD] = word
                grammer_dict[TSPKeys.SYNONYMS] = synonyms
                grammar_list.append(grammer_dict)
                grammer_dict = {}

        output[TSPKeys.PROMPT] = prompt.prompt
        output[TSPKeys.ACTIVE] = prompt.active
        output[TSPKeys.CHUNK_SIZE] = profile_manager.chunk_size
        output[TSPKeys.VECTOR_DB] = vector_db
        output[TSPKeys.EMBEDDING] = embedding_model
        output[TSPKeys.CHUNK_OVERLAP] = profile_manager.chunk_overlap
        output[TSPKeys.LLM] = llm
        output[TSPKeys.TYPE] = prompt.enforce_type
        output[TSPKeys.NAME] = prompt.prompt_key
        output[TSPKeys.RETRIEVAL_STRATEGY] = profile_manager.retrieval_strategy
        output[TSPKeys.SIMILARITY_TOP_K] = profile_manager.similarity_top_k
        output[TSPKeys.SECTION] = profile_manager.section
        output[TSPKeys.X2TEXT_ADAPTER] = x2text
        # Eval settings for the prompt
        output[TSPKeys.EVAL_SETTINGS] = {}
        output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_EVALUATE] = prompt.evaluate
        output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_MONITOR_LLM] = [monitor_llm]
        output[TSPKeys.EVAL_SETTINGS][
            TSPKeys.EVAL_SETTINGS_EXCLUDE_FAILED
        ] = tool.exclude_failed
        for attr in dir(prompt):
            if attr.startswith(TSPKeys.EVAL_METRIC_PREFIX):
                attr_val = getattr(prompt, attr)
                output[TSPKeys.EVAL_SETTINGS][attr] = attr_val

        output = PromptStudioHelper.fetch_table_settings_if_enabled(
            doc_name, prompt, org_id, user_id, tool_id, output
        )
        variable_map = PromptStudioVariableService.frame_variable_replacement_map(
            doc_id=document_id, prompt_object=prompt
        )
        if variable_map:
            output[TSPKeys.VARIABLE_MAP] = variable_map
        outputs.append(output)

        tool_settings = {}
        tool_settings[TSPKeys.ENABLE_CHALLENGE] = tool.enable_challenge
        tool_settings[TSPKeys.CHALLENGE_LLM] = challenge_llm
        tool_settings[TSPKeys.SINGLE_PASS_EXTRACTION_MODE] = (
            tool.single_pass_extraction_mode
        )
        tool_settings[TSPKeys.SUMMARIZE_AS_SOURCE] = tool.summarize_as_source
        tool_settings[TSPKeys.PREAMBLE] = tool.preamble
        tool_settings[TSPKeys.POSTAMBLE] = tool.postamble
        tool_settings[TSPKeys.GRAMMAR] = grammar_list
        tool_settings[TSPKeys.ENABLE_HIGHLIGHT] = tool.enable_highlight
        tool_settings[TSPKeys.PLATFORM_POSTAMBLE] = getattr(
            settings, TSPKeys.PLATFORM_POSTAMBLE.upper(), ""
        )

        file_hash = ToolUtils.get_hash_from_file(file_path=doc_path)

        payload = {
            TSPKeys.TOOL_SETTINGS: tool_settings,
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.RUN_ID: run_id,
            TSPKeys.FILE_NAME: doc_name,
            TSPKeys.FILE_HASH: file_hash,
            TSPKeys.FILE_PATH: doc_path,
            Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
        }

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        responder = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
        )
        include_metadata = {TSPKeys.INCLUDE_METADATA: True}

        answer = responder.answer_prompt(payload, include_metadata)
        # TODO: Make use of dataclasses
        if answer["status"] == "ERROR":
            # TODO: Publish to FE logs from here
            error_message = answer.get("error", "")
            raise AnswerFetchError(
                "Error while fetching response for "
                f"'{prompt.prompt_key}' with '{doc_name}'. {error_message}"
            )
        output_response = json.loads(answer["structure_output"])
        return output_response

    @staticmethod
    def fetch_table_settings_if_enabled(
        doc_name: str,
        prompt: ToolStudioPrompt,
        org_id: str,
        user_id: str,
        tool_id: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:

        if (
            prompt.enforce_type == TSPKeys.TABLE
            or prompt.enforce_type == TSPKeys.RECORD
        ):
            extract_doc_path: str = (
                PromptStudioHelper._get_extract_or_summary_document_path(
                    org_id, user_id, tool_id, doc_name, TSPKeys.EXTRACT
                )
            )
            for modifier_plugin in modifier_plugins:
                cls = modifier_plugin[ModifierConfig.METADATA][
                    ModifierConfig.METADATA_SERVICE_CLASS
                ]
                output = cls.update(
                    output=output,
                    tool_id=tool_id,
                    prompt_id=str(prompt.prompt_id),
                    prompt=prompt.prompt,
                    input_file=extract_doc_path,
                    clean_pages=True,
                )

        return output

    @staticmethod
    def dynamic_indexer(
        profile_manager: ProfileManager,
        tool_id: str,
        file_path: str,
        org_id: str,
        document_id: str,
        user_id: str,
        is_summary: bool = False,
        reindex: bool = False,
        run_id: str = None,
        process_text: Optional[Callable[[str], str]] = None,
    ) -> Any:
        """Used to index a file based on the passed arguments.

        This is useful when a file needs to be indexed dynamically as the
        parameters meant for indexing changes. The file

        Args:
            profile_manager (ProfileManager): Profile manager instance that hold
                values such as chunk size, chunk overlap and adapter IDs
            tool_id (str): UUID of the prompt studio tool
            file_path (str): Path to the file that needs to be indexed
            org_id (str): ID of the organization
            is_summary (bool, optional): Flag to ensure if extracted contents
                need to be persisted.  Defaults to False.
            user_id (str): The ID of the user who uploaded the document

        Returns:
            str: Index key for the combination of arguments
        """
        embedding_model = str(profile_manager.embedding_model.id)
        vector_db = str(profile_manager.vector_store.id)
        x2text_adapter = str(profile_manager.x2text.id)
        extract_file_path: Optional[str] = None
        directory, filename = os.path.split(file_path)
        if not is_summary:
            extract_file_path = os.path.join(
                directory, "extract", os.path.splitext(filename)[0] + ".txt"
            )
        else:
            profile_manager.chunk_size = 0

        try:

            usage_kwargs = {"run_id": run_id}
            # Orginal file name with which file got uploaded in prompt studio
            usage_kwargs["file_name"] = filename
            util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
            tool_index = Index(tool=util)
            doc_id_key = tool_index.generate_index_key(
                vector_db=vector_db,
                embedding=embedding_model,
                x2text=x2text_adapter,
                chunk_size=str(profile_manager.chunk_size),
                chunk_overlap=str(profile_manager.chunk_overlap),
                file_path=file_path,
                file_hash=None,
            )
            if not reindex:
                indexed_doc_id = DocumentIndexingService.get_indexed_document_id(
                    org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
                )
                if indexed_doc_id:
                    return {
                        "status": IndexingStatus.COMPLETED_STATUS.value,
                        "output": indexed_doc_id,
                    }
                # Polling if document is already being indexed
                if DocumentIndexingService.is_document_indexing(
                    org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
                ):
                    return {
                        "status": IndexingStatus.PENDING_STATUS.value,
                        "output": IndexingStatus.DOCUMENT_BEING_INDEXED.value,
                    }

            # Set the document as being indexed
            DocumentIndexingService.set_document_indexing(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key
            )
            doc_id: str = tool_index.index(
                tool_id=tool_id,
                embedding_instance_id=embedding_model,
                vector_db_instance_id=vector_db,
                x2text_instance_id=x2text_adapter,
                file_path=file_path,
                chunk_size=profile_manager.chunk_size,
                chunk_overlap=profile_manager.chunk_overlap,
                reindex=reindex,
                output_file_path=extract_file_path,
                usage_kwargs=usage_kwargs.copy(),
                process_text=process_text,
            )

            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                is_summary=is_summary,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )
            DocumentIndexingService.mark_document_indexed(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
            )
            return {"status": IndexingStatus.COMPLETED_STATUS.value, "output": doc_id}
        except (IndexingError, IndexingAPIError, SdkError) as e:
            logger.error(f"Indexing failed : {e} ", stack_info=True, exc_info=True)
            doc_name = os.path.split(file_path)[1]
            PromptStudioHelper._publish_log(
                {"tool_id": tool_id, "run_id": run_id, "doc_name": doc_name},
                LogLevels.ERROR,
                LogLevels.RUN,
                f"Indexing failed : {e}",
            )
            raise IndexingAPIError(
                f"Error while indexing '{doc_name}'. {str(e)}"
            ) from e

    @staticmethod
    def _fetch_single_pass_response(
        tool: CustomTool,
        file_path: str,
        doc_name: str,
        prompts: list[ToolStudioPrompt],
        org_id: str,
        user_id: str,
        document_id: str,
        run_id: str = None,
        process_text: Optional[Callable[[str], str]] = None,
    ) -> Any:
        tool_id: str = str(tool.tool_id)
        outputs: list[dict[str, Any]] = []
        grammar: list[dict[str, Any]] = []
        prompt_grammar = tool.prompt_grammer
        default_profile = ProfileManager.get_default_llm_profile(tool)
        challenge_llm_instance: Optional[AdapterInstance] = tool.challenge_llm
        challenge_llm: Optional[str] = None
        # Using default profile manager llm if challenge_llm is None
        if challenge_llm_instance:
            challenge_llm = str(challenge_llm_instance.id)
        else:
            challenge_llm = str(default_profile.llm.id)
        # Need to check the user who created profile manager
        PromptStudioHelper.validate_adapter_status(default_profile)
        # has access to adapters configured in profile manager
        PromptStudioHelper.validate_profile_manager_owner_access(default_profile)
        default_profile.chunk_size = 0  # To retrive full context

        if prompt_grammar:
            for word, synonyms in prompt_grammar.items():
                grammar.append({TSPKeys.WORD: word, TSPKeys.SYNONYMS: synonyms})

        if not default_profile:
            raise DefaultProfileError()

        index_result = PromptStudioHelper.dynamic_indexer(
            profile_manager=default_profile,
            file_path=file_path,
            tool_id=tool_id,
            org_id=org_id,
            is_summary=tool.summarize_as_source,
            document_id=document_id,
            run_id=run_id,
            user_id=user_id,
            process_text=process_text,
        )
        if index_result.get("status") == IndexingStatus.PENDING_STATUS.value:
            return {
                "status": IndexingStatus.PENDING_STATUS.value,
                "message": IndexingStatus.DOCUMENT_BEING_INDEXED.value,
            }

        vector_db = str(default_profile.vector_store.id)
        embedding_model = str(default_profile.embedding_model.id)
        llm = str(default_profile.llm.id)
        x2text = str(default_profile.x2text.id)
        tool_settings = {}
        tool_settings[TSPKeys.PREAMBLE] = tool.preamble
        tool_settings[TSPKeys.POSTAMBLE] = tool.postamble
        tool_settings[TSPKeys.GRAMMAR] = grammar
        tool_settings[TSPKeys.LLM] = llm
        tool_settings[TSPKeys.X2TEXT_ADAPTER] = x2text
        tool_settings[TSPKeys.VECTOR_DB] = vector_db
        tool_settings[TSPKeys.EMBEDDING] = embedding_model
        tool_settings[TSPKeys.CHUNK_SIZE] = default_profile.chunk_size
        tool_settings[TSPKeys.CHUNK_OVERLAP] = default_profile.chunk_overlap
        tool_settings[TSPKeys.ENABLE_CHALLENGE] = tool.enable_challenge
        tool_settings[TSPKeys.ENABLE_HIGHLIGHT] = tool.enable_highlight
        tool_settings[TSPKeys.CHALLENGE_LLM] = challenge_llm

        for prompt in prompts:
            if not prompt.prompt:
                raise EmptyPromptError()
            output: dict[str, Any] = {}
            output[TSPKeys.PROMPT] = prompt.prompt
            output[TSPKeys.ACTIVE] = prompt.active
            output[TSPKeys.TYPE] = prompt.enforce_type
            output[TSPKeys.NAME] = prompt.prompt_key
            outputs.append(output)

        if tool.summarize_as_source:
            path = Path(file_path)
            file_path = str(path.parent / TSPKeys.SUMMARIZE / (path.stem + ".txt"))
        file_hash = ToolUtils.get_hash_from_file(file_path=file_path)

        payload = {
            TSPKeys.TOOL_SETTINGS: tool_settings,
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.RUN_ID: run_id,
            TSPKeys.FILE_HASH: file_hash,
            TSPKeys.FILE_NAME: doc_name,
            Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
        }

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        responder = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
        )
        include_metadata = {TSPKeys.INCLUDE_METADATA: True}

        answer = responder.single_pass_extraction(payload, include_metadata)
        # TODO: Make use of dataclasses
        if answer["status"] == "ERROR":
            error_message = answer.get("error", None)
            raise AnswerFetchError(
                f"Error while fetching response for prompt(s). {error_message}"
            )
        output_response = json.loads(answer["structure_output"])
        return output_response

    @staticmethod
    def get_tool_from_tool_id(tool_id: str) -> Optional[CustomTool]:
        try:
            tool: CustomTool = CustomTool.objects.get(tool_id=tool_id)
            return tool
        except CustomTool.DoesNotExist:
            return None
