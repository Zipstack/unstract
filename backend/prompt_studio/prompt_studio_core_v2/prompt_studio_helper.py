import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from account_v2.constants import Common
from account_v2.models import User
from adapter_processor_v2.constants import AdapterKeys
from adapter_processor_v2.models import AdapterInstance
from django.conf import settings
from django.db.models.manager import BaseManager
from rest_framework.request import Request
from utils.file_storage.constants import FileStorageKeys
from utils.file_storage.helpers.prompt_studio_file_helper import PromptStudioFileHelper
from utils.local_context import StateStore

from prompt_studio.modifier_loader import ModifierConfig
from prompt_studio.modifier_loader import load_plugins as load_modifier_plugins
from prompt_studio.processor_loader import get_plugin_class_by_name
from prompt_studio.processor_loader import load_plugins as load_processor_plugins
from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_profile_manager_v2.profile_manager_helper import (
    ProfileManagerHelper,
)
from prompt_studio.prompt_studio_core_v2.constants import (
    DefaultValues,
    ExecutionSource,
    IndexingStatus,
    LogLevels,
    ToolStudioPromptKeys,
)
from prompt_studio.prompt_studio_core_v2.constants import IndexingConstants as IKeys
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
    ExtractionAPIError,
    IndexingAPIError,
    NoPromptsFound,
    OperationNotSupported,
    PermissionError,
    ToolNotValid,
)
from prompt_studio.prompt_studio_core_v2.migration_utils import (
    SummarizeMigrationUtils,
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
from unstract.core.pubsub_helper import LogPublisher
from unstract.sdk.constants import LogLevel
from unstract.sdk.exceptions import IndexingError, SdkError
from unstract.sdk.file_storage.constants import StorageType
from unstract.sdk.file_storage.env_helper import EnvHelper
from unstract.sdk.prompt import PromptTool
from unstract.sdk.utils.indexing_utils import IndexingUtils

logger = logging.getLogger(__name__)

CHOICES_JSON = "/static/select_choices.json"
ERROR_MSG = "User %s doesn't have access to adapter %s"

logger = logging.getLogger(__name__)

modifier_plugins = load_modifier_plugins()


class PromptStudioHelper:
    """Helper class for Custom tool operations."""

    processor_plugins = load_processor_plugins()

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
        run_id: str = None,
    ) -> Any:
        """Method to index a document.

        Args:
            tool_id (str): Id of the tool
            file_name (str): File to parse
            org_id (str): The ID of the organization to which the user belongs.
            user_id (str): The ID of the user who uploaded the document.

        Raises:
            ToolNotValid
            IndexingError
        """
        tool: CustomTool = CustomTool.objects.get(pk=tool_id)
        file_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
            org_id,
            is_create=False,
            user_id=user_id,
            tool_id=tool_id,
        )
        file_path = str(Path(file_path) / file_name)

        # Always get the default profile first
        default_profile = ProfileManager.get_default_llm_profile(tool)
        summary_profile = (
            default_profile  # Constructed profile for summarization, not stored in DB
        )

        # Check if summarization is enabled and handle accordingly
        if tool.summarize_context:
            # Trigger migration if needed
            SummarizeMigrationUtils.migrate_tool_to_adapter_based(tool)

            if tool.summarize_llm_adapter:
                # For summarization with adapter-based approach, we'll use the default profile
                # but override the LLM when needed in the summarization process
                summary_profile = default_profile
            else:
                # Fallback to old profile-based approach
                try:
                    profile_manager: ProfileManager = ProfileManager.objects.get(
                        prompt_studio_tool=tool, is_summarize_llm=True
                    )
                    profile_manager.chunk_size = 0
                    summary_profile = profile_manager
                except ProfileManager.DoesNotExist:
                    # If no summarize profile exists, continue with default profile
                    logger.warning(
                        f"No summarize profile found for tool {tool_id}, using default profile"
                    )
                    summary_profile = default_profile

        if not tool:
            logger.error(f"No tool instance found for the ID {tool_id}")
            raise ToolNotValid()

        # Validate the status of adapter in profile manager
        PromptStudioHelper.validate_adapter_status(default_profile)
        # Need to check the user who created profile manager
        # has access to adapters configured in profile manager
        PromptStudioHelper.validate_profile_manager_owner_access(default_profile)

        # Also validate summary profile if it's different from default
        if tool.summarize_context and summary_profile != default_profile:
            PromptStudioHelper.validate_adapter_status(summary_profile)
            PromptStudioHelper.validate_profile_manager_owner_access(summary_profile)

        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
        doc_id = IndexingUtils.generate_index_key(
            vector_db=str(default_profile.vector_store.id),
            embedding=str(default_profile.embedding_model.id),
            x2text=str(default_profile.x2text.id),
            chunk_size=str(default_profile.chunk_size),
            chunk_overlap=str(default_profile.chunk_overlap),
            file_path=file_path,
            file_hash=None,
            fs=fs_instance,
            tool=util,
        )
        extracted_text = PromptStudioHelper.dynamic_extractor(
            profile_manager=default_profile,
            file_path=file_path,
            org_id=org_id,
            document_id=document_id,
            run_id=run_id,
            enable_highlight=tool.enable_highlight,
            doc_id=doc_id,
            reindex=True,
        )
        if tool.summarize_context:
            summarize_file_path = PromptStudioHelper.summarize(
                file_name, org_id, document_id, run_id, tool, doc_id
            )
            summarize_doc_id = IndexingUtils.generate_index_key(
                vector_db=str(summary_profile.vector_store.id),
                embedding=str(summary_profile.embedding_model.id),
                x2text=str(summary_profile.x2text.id),
                chunk_size="0",  # Summarization always uses chunk_size=0
                chunk_overlap=str(summary_profile.chunk_overlap),
                file_path=summarize_file_path,
                fs=fs_instance,
                tool=util,
            )
            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                is_summary=True,
                profile_manager=summary_profile,
                doc_id=summarize_doc_id,
            )
        start_time = time.time()
        logger.info(f"[{tool_id}] Indexing started for doc: {file_name}")
        PromptStudioHelper._publish_log(
            {"tool_id": tool_id, "run_id": run_id, "doc_name": file_name},
            LogLevels.INFO,
            LogLevels.RUN,
            "Indexing started",
        )
        PromptStudioHelper.dynamic_indexer(
            profile_manager=default_profile,
            tool_id=tool_id,
            file_path=file_path,
            org_id=org_id,
            document_id=document_id,
            reindex=True,
            run_id=run_id,
            user_id=user_id,
            enable_highlight=tool.enable_highlight,
            extracted_text=extracted_text,
            doc_id_key=doc_id,
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
        logger.info(f"Indexing successful : {doc_id}")
        return doc_id

    @staticmethod
    def summarize(file_name, org_id, document_id, run_id, tool, doc_id) -> str:
        cls = get_plugin_class_by_name(
            name="summarizer",
            plugins=PromptStudioHelper.processor_plugins,
        )
        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[ToolStudioPromptKeys.RUN_ID] = run_id
        prompts: list[ToolStudioPrompt] = PromptStudioHelper.fetch_prompt_from_tool(
            tool.tool_id
        )
        if cls:
            summarize_file_path = cls.process(
                tool_id=str(tool.tool_id),
                file_name=file_name,
                org_id=org_id,
                user_id=tool.created_by.user_id,
                usage_kwargs=usage_kwargs.copy(),
                prompts=prompts,
            )
            # Trigger migration if needed
            SummarizeMigrationUtils.migrate_tool_to_adapter_based(tool)

            # Validate that summarization is properly configured
            if not tool.summarize_llm_adapter:
                # Fallback to old approach if no adapter - just validate it exists
                try:
                    ProfileManager.objects.get(
                        prompt_studio_tool=tool, is_summarize_llm=True
                    )
                except ProfileManager.DoesNotExist:
                    logger.warning(
                        f"No summarize profile found for tool {tool.tool_id}, using default profile"
                    )

            return summarize_file_path

    @staticmethod
    def prompt_responder(
        tool_id: str,
        org_id: str,
        user_id: str,
        document_id: str,
        id: str | None = None,
        run_id: str = None,
        profile_manager_id: str | None = None,
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
            )
        else:
            return PromptStudioHelper._execute_prompts_in_single_pass(
                doc_path=doc_path,
                doc_name=doc_name,
                tool_id=tool_id,
                org_id=org_id,
                document_id=document_id,
                run_id=run_id,
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
        document_id,
        run_id,
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
        try:
            tool = prompts[0].tool_id
            response = PromptStudioHelper._fetch_single_pass_response(
                input_file_path=doc_path,
                doc_name=doc_name,
                tool=tool,
                prompts=prompts,
                org_id=org_id,
                document_id=document_id,
                run_id=run_id,
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
        doc_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
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
        doc_path = PromptStudioFileHelper.get_or_create_prompt_studio_subdirectory(
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
        profile_manager_id: str | None = None,
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

        monitor_llm_instance: AdapterInstance | None = tool.monitor_llm
        monitor_llm: str | None = None
        challenge_llm_instance: AdapterInstance | None = tool.challenge_llm
        challenge_llm: str | None = None
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
        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        file_path = doc_path
        directory, filename = os.path.split(doc_path)
        doc_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )
        is_summary = tool.summarize_as_source
        logger.info(f"Summary status : {is_summary}")
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
        logger.info(
            f"Passing file_path for fetching answer "
            f"{file_path} : extraction path {doc_path}"
        )
        doc_id = IndexingUtils.generate_index_key(
            vector_db=str(profile_manager.vector_store.id),
            embedding=str(profile_manager.embedding_model.id),
            x2text=str(profile_manager.x2text.id),
            chunk_size=str(profile_manager.chunk_size),
            chunk_overlap=str(profile_manager.chunk_overlap),
            file_path=file_path,
            file_hash=None,
            fs=fs_instance,
            tool=util,
        )
        if DocumentIndexingService.is_document_indexing(
            org_id=org_id, user_id=user_id, doc_id_key=doc_id
        ):
            return {
                "status": IndexingStatus.PENDING_STATUS.value,
                "output": IndexingStatus.DOCUMENT_BEING_INDEXED.value,
            }
        logger.info(f"Extracting text from {file_path} for {doc_id}")
        extracted_text = PromptStudioHelper.dynamic_extractor(
            profile_manager=profile_manager,
            file_path=file_path,
            org_id=org_id,
            document_id=document_id,
            run_id=run_id,
            enable_highlight=tool.enable_highlight,
            doc_id=doc_id,
        )
        logger.info(f"Extracted text from {file_path} for {doc_id}")
        if is_summary:
            profile_manager.chunk_size = 0
            doc_path = Path(doc_path)  # Convert string to Path object
            doc_path = str(
                doc_path.parent.parent / "summarize" / (doc_path.stem + ".txt")
            )
            logger.info("Summary enabled, set chunk to zero..")
        logger.info(f"Indexing document {doc_path} for {doc_id}")
        index_result = PromptStudioHelper.dynamic_indexer(
            profile_manager=profile_manager,
            file_path=file_path,
            tool_id=str(tool.tool_id),
            org_id=org_id,
            document_id=document_id,
            run_id=run_id,
            user_id=user_id,
            enable_highlight=tool.enable_highlight,
            extracted_text=extracted_text,
            doc_id_key=doc_id,
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
        output[TSPKeys.REQUIRED] = prompt.required
        logger.info(f"Chunk size set to {profile_manager.chunk_size} ")
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
        # Webhook postprocessing settings
        webhook_enabled = bool(prompt.enable_postprocessing_webhook)
        webhook_url = (prompt.postprocessing_webhook_url or "").strip()
        if webhook_enabled and not webhook_url:
            logger.warning(
                "Postprocessing webhook enabled but URL missing for prompt %s; disabling.",
                prompt.prompt_key,
            )
            webhook_enabled = False
        output[TSPKeys.ENABLE_POSTPROCESSING_WEBHOOK] = webhook_enabled
        if webhook_enabled:
            output[TSPKeys.POSTPROCESSING_WEBHOOK_URL] = webhook_url
        # Eval settings for the prompt
        output[TSPKeys.EVAL_SETTINGS] = {}
        output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_EVALUATE] = prompt.evaluate
        output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_MONITOR_LLM] = [monitor_llm]
        output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_EXCLUDE_FAILED] = (
            tool.exclude_failed
        )
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
        file_hash = fs_instance.get_hash_from_file(path=doc_path)

        payload = {
            TSPKeys.TOOL_SETTINGS: tool_settings,
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.RUN_ID: run_id,
            TSPKeys.FILE_NAME: doc_name,
            TSPKeys.FILE_HASH: file_hash,
            TSPKeys.FILE_PATH: doc_path,
            Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
            TSPKeys.EXECUTION_SOURCE: ExecutionSource.IDE.value,
        }

        try:
            responder = PromptTool(
                tool=util,
                prompt_host=settings.PROMPT_HOST,
                prompt_port=settings.PROMPT_PORT,
                request_id=StateStore.get(Common.REQUEST_ID),
            )
            params = {TSPKeys.INCLUDE_METADATA: True}
            return responder.answer_prompt(payload=payload, params=params)
        except SdkError as e:
            msg = str(e)
            if e.actual_err and hasattr(e.actual_err, "response"):
                msg = e.actual_err.response.json().get("error", str(e))
            raise AnswerFetchError(
                "Error while fetching response for "
                f"'{prompt.prompt_key}' with '{doc_name}'. {msg}",
                status_code=int(e.status_code or 500),
            )

    @staticmethod
    def fetch_table_settings_if_enabled(
        doc_name: str,
        prompt: ToolStudioPrompt,
        org_id: str,
        user_id: str,
        tool_id: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        if prompt.enforce_type == TSPKeys.TABLE or prompt.enforce_type == TSPKeys.RECORD:
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
        extracted_text: str,
        reindex: bool = False,
        run_id: str = None,
        enable_highlight: bool = False,
        doc_id_key: str | None = None,
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
        if profile_manager.chunk_size == 0:
            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                profile_manager=profile_manager,
                doc_id=doc_id_key,
            )
            logger.info("Skipping addition of nodes to VectoDB since chunk size is 0")
            return {
                "status": IndexingStatus.COMPLETED_STATUS.value,
                "output": doc_id_key,
            }

        embedding_model = str(profile_manager.embedding_model.id)
        vector_db = str(profile_manager.vector_store.id)
        x2text_adapter = str(profile_manager.x2text.id)
        directory, filename = os.path.split(file_path)
        file_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )
        try:
            usage_kwargs = {"run_id": run_id}
            # Orginal file name with which file got uploaded in prompt studio
            usage_kwargs["file_name"] = filename

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
            logger.info(f"Invoking prompt service for indexing : {doc_id_key}")
            payload = {
                IKeys.TOOL_ID: tool_id,
                IKeys.EMBEDDING_INSTANCE_ID: embedding_model,
                IKeys.VECTOR_DB_INSTANCE_ID: vector_db,
                IKeys.X2TEXT_INSTANCE_ID: x2text_adapter,
                IKeys.FILE_PATH: file_path,
                IKeys.FILE_HASH: None,
                IKeys.CHUNK_OVERLAP: profile_manager.chunk_overlap,
                IKeys.CHUNK_SIZE: profile_manager.chunk_size,
                IKeys.REINDEX: reindex,
                IKeys.ENABLE_HIGHLIGHT: enable_highlight,
                IKeys.USAGE_KWARGS: usage_kwargs.copy(),
                IKeys.EXTRACTED_TEXT: extracted_text,
                IKeys.RUN_ID: run_id,
                Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
                TSPKeys.EXECUTION_SOURCE: ExecutionSource.IDE.value,
            }

            util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

            try:
                responder = PromptTool(
                    tool=util,
                    prompt_host=settings.PROMPT_HOST,
                    prompt_port=settings.PROMPT_PORT,
                    request_id=StateStore.get(Common.REQUEST_ID),
                )
                doc_id = responder.index(payload=payload)
            except SdkError as e:
                msg = str(e)
                if e.actual_err and hasattr(e.actual_err, "response"):
                    msg = e.actual_err.response.json().get("error", str(e))
                raise IndexingAPIError(
                    f"Failed to index '{filename}'. {msg}",
                    status_code=int(e.status_code or 500),
                )

            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )
            DocumentIndexingService.mark_document_indexed(
                org_id=org_id, user_id=user_id, doc_id_key=doc_id_key, doc_id=doc_id
            )
            return {"status": IndexingStatus.COMPLETED_STATUS.value, "output": doc_id}
        except (IndexingError, IndexingAPIError, SdkError) as e:
            msg = str(e)
            if isinstance(e, SdkError) and hasattr(e.actual_err, "response"):
                msg = e.actual_err.response.json().get("error", str(e))

            msg = f"Error while indexing '{filename}'. {msg}"
            logger.error(msg, stack_info=True, exc_info=True)
            PromptStudioHelper._publish_log(
                {"tool_id": tool_id, "run_id": run_id, "doc_name": filename},
                LogLevels.ERROR,
                LogLevels.RUN,
                msg,
            )
            raise IndexingAPIError(msg) from e

    @staticmethod
    def _fetch_single_pass_response(
        tool: CustomTool,
        input_file_path: str,
        doc_name: str,
        prompts: list[ToolStudioPrompt],
        org_id: str,
        document_id: str,
        run_id: str = None,
    ) -> Any:
        tool_id: str = str(tool.tool_id)
        outputs: list[dict[str, Any]] = []
        grammar: list[dict[str, Any]] = []
        prompt_grammar = tool.prompt_grammer
        default_profile = ProfileManager.get_default_llm_profile(tool)
        challenge_llm_instance: AdapterInstance | None = tool.challenge_llm
        challenge_llm: str | None = None
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
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
        if prompt_grammar:
            for word, synonyms in prompt_grammar.items():
                grammar.append({TSPKeys.WORD: word, TSPKeys.SYNONYMS: synonyms})

        if not default_profile:
            raise DefaultProfileError()

        fs_instance = EnvHelper.get_storage(
            storage_type=StorageType.PERMANENT,
            env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
        )
        directory, filename = os.path.split(input_file_path)
        file_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )
        doc_id = IndexingUtils.generate_index_key(
            vector_db=str(default_profile.vector_store.id),
            embedding=str(default_profile.embedding_model.id),
            x2text=str(default_profile.x2text.id),
            chunk_size=str(default_profile.chunk_size),
            chunk_overlap=str(default_profile.chunk_overlap),
            file_path=input_file_path,
            file_hash=None,
            fs=fs_instance,
            tool=util,
        )
        PromptStudioHelper.dynamic_extractor(
            profile_manager=default_profile,
            file_path=input_file_path,
            org_id=org_id,
            document_id=document_id,
            run_id=run_id,
            enable_highlight=tool.enable_highlight,
            doc_id=doc_id,
        )
        # Indexing is not needed as Single pass is always non chunked.
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
        tool_settings[TSPKeys.PLATFORM_POSTAMBLE] = getattr(
            settings, TSPKeys.PLATFORM_POSTAMBLE.upper(), ""
        )
        tool_settings[TSPKeys.SUMMARIZE_AS_SOURCE] = tool.summarize_as_source
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
            file_path = str(path.parent.parent / TSPKeys.SUMMARIZE / (path.stem + ".txt"))
        file_hash = fs_instance.get_hash_from_file(path=file_path)
        logger.info("payload constructued, calling prompt service..")
        payload = {
            TSPKeys.TOOL_SETTINGS: tool_settings,
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.RUN_ID: run_id,
            TSPKeys.FILE_HASH: file_hash,
            TSPKeys.FILE_NAME: doc_name,
            TSPKeys.FILE_PATH: file_path,
            Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
            TSPKeys.EXECUTION_SOURCE: ExecutionSource.IDE.value,
        }

        responder = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
            request_id=StateStore.get(Common.REQUEST_ID),
        )
        params = {TSPKeys.INCLUDE_METADATA: True}
        return responder.single_pass_extraction(payload=payload, params=params)

    @staticmethod
    def get_tool_from_tool_id(tool_id: str) -> CustomTool | None:
        try:
            tool: CustomTool = CustomTool.objects.get(tool_id=tool_id)
            return tool
        except CustomTool.DoesNotExist:
            return None

    @staticmethod
    def dynamic_extractor(
        file_path: str,
        enable_highlight: bool,
        run_id: str,
        org_id: str,
        profile_manager: ProfileManager,
        document_id: str,
        doc_id: str,
        reindex: bool | None = False,
    ) -> str:
        x2text = str(profile_manager.x2text.id)
        is_extracted: bool = False
        extract_file_path: str | None = None
        extracted_text = ""
        directory, filename = os.path.split(file_path)
        extract_file_path = os.path.join(
            directory, "extract", os.path.splitext(filename)[0] + ".txt"
        )
        usage_kwargs = {"run_id": run_id}
        # Orginal file name with which file got uploaded in prompt studio
        usage_kwargs["file_name"] = filename
        is_extracted = PromptStudioIndexHelper.check_extraction_status(
            document_id=document_id,
            profile_manager=profile_manager,
            doc_id=doc_id,
        )
        if is_extracted and not reindex:
            fs_instance = EnvHelper.get_storage(
                storage_type=StorageType.PERMANENT,
                env_name=FileStorageKeys.PERMANENT_REMOTE_STORAGE,
            )
            try:
                extracted_text = fs_instance.read(path=extract_file_path, mode="r")
                logger.info("Extracted text found. Reading from file..")
                return extracted_text
            except FileNotFoundError as e:
                logger.warning(
                    f"File not found for extraction. {extract_file_path}. {e}"
                    "Continuing extraction.."
                )
                extracted_text = None
        payload = {
            IKeys.X2TEXT_INSTANCE_ID: x2text,
            IKeys.FILE_PATH: file_path,
            IKeys.ENABLE_HIGHLIGHT: enable_highlight,
            IKeys.USAGE_KWARGS: usage_kwargs.copy(),
            IKeys.RUN_ID: run_id,
            Common.LOG_EVENTS_ID: StateStore.get(Common.LOG_EVENTS_ID),
            TSPKeys.EXECUTION_SOURCE: ExecutionSource.IDE.value,
            IKeys.OUTPUT_FILE_PATH: extract_file_path,
        }

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        try:
            responder = PromptTool(
                tool=util,
                prompt_host=settings.PROMPT_HOST,
                prompt_port=settings.PROMPT_PORT,
                request_id=StateStore.get(Common.REQUEST_ID),
            )
            extracted_text = responder.extract(payload=payload)
            PromptStudioIndexHelper.mark_extraction_status(
                document_id=document_id,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )
        except SdkError as e:
            msg = str(e)
            if e.actual_err and hasattr(e.actual_err, "response"):
                msg = e.actual_err.response.json().get("error", str(e))
            raise ExtractionAPIError(
                f"Failed to extract '{filename}'. {msg}",
                status_code=int(e.status_code or 500),
            )

        return extracted_text

    @staticmethod
    def export_project_settings(tool: CustomTool) -> dict:
        """Export project settings as a comprehensive JSON structure.

        Args:
            tool (CustomTool): The CustomTool instance to export

        Returns:
            dict: Complete project configuration including tool settings and prompts
        """
        return {
            "tool_metadata": PromptStudioHelper._export_tool_metadata(tool),
            "tool_settings": PromptStudioHelper._export_tool_settings(tool),
            "default_profile_settings": PromptStudioHelper._export_default_profile_settings(
                tool
            ),
            "prompts": PromptStudioHelper._export_prompts(tool),
            "export_metadata": PromptStudioHelper._export_metadata(tool),
        }

    @staticmethod
    def _export_tool_metadata(tool: CustomTool) -> dict:
        """Export tool metadata information.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            dict: Tool metadata configuration
        """
        return {
            "tool_name": tool.tool_name,
            "description": tool.description,
            "author": tool.author,
            "icon": tool.icon,
        }

    @staticmethod
    def _export_tool_settings(tool: CustomTool) -> dict:
        """Export tool settings configuration.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            dict: Tool settings configuration
        """
        return {
            "preamble": tool.preamble,
            "postamble": tool.postamble,
            "summarize_prompt": tool.summarize_prompt,
            "summarize_context": tool.summarize_context,
            "summarize_as_source": tool.summarize_as_source,
            "enable_challenge": tool.enable_challenge,
            "enable_highlight": tool.enable_highlight,
            "exclude_failed": tool.exclude_failed,
            "single_pass_extraction_mode": tool.single_pass_extraction_mode,
            "prompt_grammer": tool.prompt_grammer,
        }

    @staticmethod
    def _export_default_profile_settings(tool: CustomTool) -> dict:
        """Export default profile settings with safe fallbacks.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            dict: Default profile configuration
        """
        default_profile = PromptStudioHelper._get_default_profile(tool)

        return {
            "chunk_size": default_profile.chunk_size
            if default_profile
            else DefaultValues.DEFAULT_CHUNK_SIZE,
            "chunk_overlap": default_profile.chunk_overlap
            if default_profile
            else DefaultValues.DEFAULT_CHUNK_OVERLAP,
            "retrieval_strategy": (
                default_profile.retrieval_strategy
                if default_profile
                else DefaultValues.DEFAULT_RETRIEVAL_STRATEGY
            ),
            "similarity_top_k": (
                default_profile.similarity_top_k
                if default_profile
                else DefaultValues.DEFAULT_SIMILARITY_TOP_K
            ),
            "section": default_profile.section
            if default_profile
            else DefaultValues.DEFAULT_SECTION,
            "profile_name": (
                default_profile.profile_name
                if default_profile
                else DefaultValues.DEFAULT_PROFILE_NAME
            ),
        }

    @staticmethod
    def _get_default_profile(tool: CustomTool) -> ProfileManager | None:
        """Safely retrieve the default profile for a tool.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            ProfileManager | None: Default profile or None if not found
        """
        try:
            return ProfileManager.objects.filter(
                prompt_studio_tool=tool, is_default=True
            ).first()
        except Exception as e:
            logger.warning(
                f"Failed to retrieve default profile for tool {tool.tool_id}: {e}"
            )
            return None

    @staticmethod
    def _export_prompts(tool: CustomTool) -> list[dict]:
        """Export all prompts for the tool.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            list[dict]: List of prompt configurations
        """
        prompts = PromptStudioHelper.fetch_prompt_from_tool(str(tool.tool_id))
        return [PromptStudioHelper._export_single_prompt(prompt) for prompt in prompts]

    @staticmethod
    def _export_single_prompt(prompt: ToolStudioPrompt) -> dict:
        """Export a single prompt configuration.

        Args:
            prompt (ToolStudioPrompt): The prompt instance to export

        Returns:
            dict: Prompt configuration
        """
        return {
            "prompt_key": prompt.prompt_key,
            "prompt": prompt.prompt,
            "active": prompt.active,
            "required": prompt.required,
            "enforce_type": prompt.enforce_type,
            "sequence_number": prompt.sequence_number,
            "prompt_type": prompt.prompt_type,
            "assert_prompt": prompt.assert_prompt,
            "assertion_failure_prompt": prompt.assertion_failure_prompt,
            "is_assert": prompt.is_assert,
            "evaluate": prompt.evaluate,
            "eval_quality_faithfulness": prompt.eval_quality_faithfulness,
            "eval_quality_correctness": prompt.eval_quality_correctness,
            "eval_quality_relevance": prompt.eval_quality_relevance,
            "eval_security_pii": prompt.eval_security_pii,
            "eval_guidance_toxicity": prompt.eval_guidance_toxicity,
            "eval_guidance_completeness": prompt.eval_guidance_completeness,
            "enable_postprocessing_webhook": prompt.enable_postprocessing_webhook,
            "postprocessing_webhook_url": prompt.postprocessing_webhook_url,
        }

    @staticmethod
    def _export_metadata(tool: CustomTool) -> dict:
        """Export metadata about the export itself.

        Args:
            tool (CustomTool): The CustomTool instance

        Returns:
            dict: Export metadata
        """
        return {
            "exported_at": tool.modified_at.isoformat() if tool.modified_at else None,
            "tool_id": str(tool.tool_id),
        }

    @staticmethod
    def validate_import_file(request: Request) -> tuple[dict, dict]:
        """Validate uploaded file and extract import data.

        Returns:
            tuple: (import_data, selected_adapters)
        """
        if "file" not in request.FILES:
            raise ValueError("No file provided")

        file = request.FILES["file"]

        if not file.name.endswith(".json"):
            raise ValueError("Only JSON files are supported")

        try:
            import_data = json.loads(file.read().decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON file")

        required_keys = ["tool_metadata", "tool_settings", "prompts"]
        if not all(key in import_data for key in required_keys):
            raise ValueError("Invalid project file structure")

        selected_adapters = {
            "llm_adapter_id": request.data.get("llm_adapter_id"),
            "vector_db_adapter_id": request.data.get("vector_db_adapter_id"),
            "embedding_adapter_id": request.data.get("embedding_adapter_id"),
            "x2text_adapter_id": request.data.get("x2text_adapter_id"),
        }

        return import_data, selected_adapters

    @staticmethod
    def generate_unique_tool_name(base_name: str, organization) -> str:
        """Generate a unique tool name for import.

        Args:
            base_name: Original tool name from import data
            organization: Organization instance

        Returns:
            str: Unique tool name
        """
        tool_name = base_name
        counter = 1

        while CustomTool.objects.filter(
            tool_name=tool_name,
            organization=organization,
        ).exists():
            tool_name = f"{base_name} (imported {counter})"
            counter += 1

        return tool_name

    @staticmethod
    def create_tool_from_import_data(
        import_data: dict, tool_name: str, organization, user
    ) -> CustomTool:
        """Create a new CustomTool from import data.

        Args:
            import_data: Parsed JSON data from import file
            tool_name: Unique tool name
            organization: Organization instance
            user: User creating the tool

        Returns:
            CustomTool: Created tool instance
        """
        tool_metadata = import_data["tool_metadata"]
        tool_settings = import_data["tool_settings"]

        return CustomTool.objects.create(
            tool_name=tool_name,
            description=tool_metadata["description"],
            author=tool_metadata["author"],
            icon=tool_metadata.get("icon", DefaultValues.DEFAULT_ICON),
            preamble=tool_settings.get("preamble", DefaultValues.DEFAULT_PREAMBLE),
            postamble=tool_settings.get("postamble", DefaultValues.DEFAULT_POSTAMBLE),
            summarize_prompt=tool_settings.get(
                "summarize_prompt", DefaultValues.DEFAULT_SUMMARIZE_PROMPT
            ),
            summarize_context=tool_settings.get(
                "summarize_context", DefaultValues.DEFAULT_SUMMARIZE_CONTEXT
            ),
            summarize_as_source=tool_settings.get(
                "summarize_as_source", DefaultValues.DEFAULT_SUMMARIZE_AS_SOURCE
            ),
            enable_challenge=tool_settings.get(
                "enable_challenge", DefaultValues.DEFAULT_ENABLE_CHALLENGE
            ),
            enable_highlight=tool_settings.get(
                "enable_highlight", DefaultValues.DEFAULT_ENABLE_HIGHLIGHT
            ),
            exclude_failed=tool_settings.get(
                "exclude_failed", DefaultValues.DEFAULT_EXCLUDE_FAILED
            ),
            single_pass_extraction_mode=tool_settings.get(
                "single_pass_extraction_mode",
                DefaultValues.DEFAULT_SINGLE_PASS_EXTRACTION_MODE,
            ),
            prompt_grammer=tool_settings.get("prompt_grammer"),
            created_by=user,
            modified_by=user,
            organization=organization,
        )

    @staticmethod
    def create_profile_manager(
        import_data: dict, selected_adapters: dict, new_tool: CustomTool, user
    ) -> None:
        """Create profile manager with imported settings and selected adapters.

        Args:
            import_data: Parsed JSON data from import file
            selected_adapters: Dictionary of selected adapter IDs
            new_tool: Created tool instance
            user: User creating the profile
        """
        profile_settings = import_data.get("default_profile_settings", {})

        if all(selected_adapters.values()):
            PromptStudioHelper._create_profile_with_selected_adapters(
                profile_settings, selected_adapters, new_tool, user
            )
        else:
            PromptStudioHelper._create_default_profile_with_settings(
                profile_settings, new_tool, user
            )

    @staticmethod
    def _create_profile_with_selected_adapters(
        profile_settings: dict, selected_adapters: dict, new_tool: CustomTool, user
    ) -> None:
        """Create profile manager with user-selected adapters."""
        try:
            llm_adapter = AdapterInstance.objects.get(
                id=selected_adapters["llm_adapter_id"]
            )
            vector_db_adapter = AdapterInstance.objects.get(
                id=selected_adapters["vector_db_adapter_id"]
            )
            embedding_adapter = AdapterInstance.objects.get(
                id=selected_adapters["embedding_adapter_id"]
            )
            x2text_adapter = AdapterInstance.objects.get(
                id=selected_adapters["x2text_adapter_id"]
            )

            ProfileManager.objects.create(
                profile_name=profile_settings.get(
                    "profile_name", DefaultValues.DEFAULT_PROFILE_NAME
                ),
                vector_store=vector_db_adapter,
                embedding_model=embedding_adapter,
                llm=llm_adapter,
                x2text=x2text_adapter,
                chunk_size=profile_settings.get(
                    "chunk_size", DefaultValues.DEFAULT_CHUNK_SIZE
                ),
                chunk_overlap=profile_settings.get(
                    "chunk_overlap", DefaultValues.DEFAULT_CHUNK_OVERLAP
                ),
                retrieval_strategy=profile_settings.get(
                    "retrieval_strategy", DefaultValues.DEFAULT_RETRIEVAL_STRATEGY
                ),
                similarity_top_k=profile_settings.get(
                    "similarity_top_k", DefaultValues.DEFAULT_SIMILARITY_TOP_K
                ),
                section=profile_settings.get("section", DefaultValues.DEFAULT_SECTION),
                prompt_studio_tool=new_tool,
                is_default=True,
                created_by=user,
                modified_by=user,
            )
        except AdapterInstance.DoesNotExist as e:
            raise ValueError(f"One or more selected adapters not found: {e}")

    @staticmethod
    def _create_default_profile_with_settings(
        profile_settings: dict, new_tool: CustomTool, user
    ) -> None:
        """Create default profile and update with imported settings."""
        PromptStudioHelper.create_default_profile_manager(
            user=user, tool_id=new_tool.tool_id
        )

        if profile_settings:
            try:
                default_profile = ProfileManager.objects.filter(
                    prompt_studio_tool=new_tool, is_default=True
                ).first()

                if default_profile:
                    default_profile.chunk_size = profile_settings.get(
                        "chunk_size", DefaultValues.DEFAULT_CHUNK_SIZE
                    )
                    default_profile.chunk_overlap = profile_settings.get(
                        "chunk_overlap", DefaultValues.DEFAULT_CHUNK_OVERLAP
                    )
                    default_profile.retrieval_strategy = profile_settings.get(
                        "retrieval_strategy", DefaultValues.DEFAULT_RETRIEVAL_STRATEGY
                    )
                    default_profile.similarity_top_k = profile_settings.get(
                        "similarity_top_k", DefaultValues.DEFAULT_SIMILARITY_TOP_K
                    )
                    default_profile.section = profile_settings.get(
                        "section", DefaultValues.DEFAULT_SECTION
                    )
                    default_profile.profile_name = profile_settings.get(
                        "profile_name", DefaultValues.DEFAULT_PROFILE_NAME
                    )
                    default_profile.save()
            except Exception as e:
                logger.warning(f"Could not update profile settings: {e}")

    @staticmethod
    def import_prompts(prompts_data: list, new_tool: CustomTool, user) -> None:
        """Import prompts from import data.

        Args:
            prompts_data: List of prompt data from import file
            new_tool: Created tool instance
            user: User creating the prompts
        """
        default_profile = ProfileManager.objects.filter(
            prompt_studio_tool=new_tool, is_default=True
        ).first()

        for prompt_data in prompts_data:
            ToolStudioPrompt.objects.create(
                prompt_key=prompt_data["prompt_key"],
                prompt=prompt_data["prompt"],
                active=prompt_data.get("active", DefaultValues.DEFAULT_ACTIVE),
                required=prompt_data.get("required", DefaultValues.DEFAULT_REQUIRED),
                enforce_type=prompt_data.get(
                    "enforce_type", DefaultValues.DEFAULT_ENFORCE_TYPE
                ),
                sequence_number=prompt_data.get("sequence_number"),
                prompt_type=prompt_data.get("prompt_type"),
                assert_prompt=prompt_data.get("assert_prompt"),
                assertion_failure_prompt=prompt_data.get("assertion_failure_prompt"),
                is_assert=prompt_data.get("is_assert", DefaultValues.DEFAULT_IS_ASSERT),
                evaluate=prompt_data.get("evaluate", DefaultValues.DEFAULT_EVALUATE),
                eval_quality_faithfulness=prompt_data.get(
                    "eval_quality_faithfulness",
                    DefaultValues.DEFAULT_EVAL_QUALITY_FAITHFULNESS,
                ),
                eval_quality_correctness=prompt_data.get(
                    "eval_quality_correctness",
                    DefaultValues.DEFAULT_EVAL_QUALITY_CORRECTNESS,
                ),
                eval_quality_relevance=prompt_data.get(
                    "eval_quality_relevance", DefaultValues.DEFAULT_EVAL_QUALITY_RELEVANCE
                ),
                eval_security_pii=prompt_data.get(
                    "eval_security_pii", DefaultValues.DEFAULT_EVAL_SECURITY_PII
                ),
                eval_guidance_toxicity=prompt_data.get(
                    "eval_guidance_toxicity", DefaultValues.DEFAULT_EVAL_GUIDANCE_TOXICITY
                ),
                eval_guidance_completeness=prompt_data.get(
                    "eval_guidance_completeness",
                    DefaultValues.DEFAULT_EVAL_GUIDANCE_COMPLETENESS,
                ),
                enable_postprocessing_webhook=prompt_data.get(
                    "enable_postprocessing_webhook", False
                ),
                postprocessing_webhook_url=prompt_data.get("postprocessing_webhook_url"),
                tool_id=new_tool,
                profile_manager=default_profile,
                created_by=user,
                modified_by=user,
            )

    @staticmethod
    def validate_adapter_configuration(
        selected_adapters: dict, new_tool: CustomTool
    ) -> tuple[bool, str]:
        """Validate adapter configuration and determine if config is needed.

        Args:
            selected_adapters: Dictionary of selected adapter IDs
            new_tool: Created tool instance

        Returns:
            tuple: (needs_adapter_config, warning_message)
        """
        if all(selected_adapters.values()):
            return False, ""

        try:
            default_profile = ProfileManager.objects.filter(
                prompt_studio_tool=new_tool, is_default=True
            ).first()

            if default_profile:
                adapters_to_check = [
                    default_profile.llm,
                    default_profile.vector_store,
                    default_profile.embedding_model,
                    default_profile.x2text,
                ]

                for adapter in adapters_to_check:
                    if not adapter or not adapter.is_usable:
                        warning_message = (
                            "Some adapters may need to be configured before you can use "
                            "this project. Please check the profile settings."
                        )
                        return True, warning_message
        except Exception:
            warning_message = (
                "Some adapters may need to be configured before you can use "
                "this project. Please check the profile settings."
            )
            return True, warning_message

        return False, ""
