import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from adapter_processor.models import AdapterInstance
from django.conf import settings
from django.core.exceptions import PermissionDenied
from file_management.file_management_helper import FileManagerHelper
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio.models import ToolStudioPrompt
from prompt_studio.prompt_studio_core.constants import LogLevels
from prompt_studio.prompt_studio_core.constants import (
    ToolStudioPromptKeys as TSPKeys,
)
from prompt_studio.prompt_studio_core.exceptions import (
    AnswerFetchError,
    DefaultProfileError,
    IndexingError,
    NoPromptsFound,
    PromptNotValid,
    ToolNotValid,
)
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_core.prompt_ide_base_tool import (
    PromptIdeBaseTool,
)
from prompt_studio.prompt_studio_index_manager.prompt_studio_index_helper import (  # noqa: E501
    PromptStudioIndexHelper,
)
from unstract.sdk.constants import LogLevel
from unstract.sdk.exceptions import SdkError
from unstract.sdk.index import ToolIndex
from unstract.sdk.prompt import PromptTool
from unstract.sdk.utils.tool_utils import ToolUtils

from unstract.core.pubsub_helper import LogHelper as stream_log

CHOICES_JSON = "/static/select_choices.json"

logger = logging.getLogger(__name__)


class PromptStudioHelper:
    """Helper class for Custom tool operations."""

    @staticmethod
    def validate_profile_manager_owner_access(
        profile_manager: ProfileManager,
    ) -> None:
        """Helper method to validate the owner's access to the profile manager.

        Args:
            profile_manager (ProfileManager): The profile manager instance to
              validate.

        Raises:
            PermissionDenied: If the owner does not have permission to perform
              the action.
        """
        profile_manager_owner = profile_manager.created_by

        if not (
            (
                profile_manager.llm.created_by == profile_manager_owner
                or profile_manager.llm.shared_users.filter(
                    pk=profile_manager_owner.pk
                ).exists()
            )
            and (
                profile_manager.vector_store.created_by == profile_manager_owner
                or profile_manager.vector_store.shared_users.filter(
                    pk=profile_manager_owner.pk
                ).exists()
            )
            and (
                profile_manager.embedding_model.created_by
                == profile_manager_owner
                or profile_manager.embedding_model.shared_users.filter(
                    pk=profile_manager_owner.pk
                ).exists()
            )
            and (
                profile_manager.x2text.created_by == profile_manager_owner
                or profile_manager.x2text.shared_users.filter(
                    pk=profile_manager_owner.pk
                ).exists()
            )
        ):
            raise PermissionDenied(
                "You don't have permission to perform this action."
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
        prompt_instances: list[ToolStudioPrompt] = (
            ToolStudioPrompt.objects.filter(tool_id=tool_id)
        )
        return prompt_instances

    @staticmethod
    def index_document(
        tool_id: str,
        file_name: str,
        org_id: str,
        user_id: str,
        document_id: str,
        is_summary: bool = False,
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
            profile_manager = ProfileManager.objects.get(
                prompt_studio_tool=tool, is_summarize_llm=True
            )
            default_profile = profile_manager
            file_path = file_name
        else:
            profile_manager = ProfileManager.objects.get(
                prompt_studio_tool=tool, is_default=True
            )
            default_profile = profile_manager
            file_path = FileManagerHelper.handle_sub_directory_for_tenants(
                org_id, is_create=False, user_id=user_id, tool_id=tool_id
            )
            file_path = str(Path(file_path) / file_name)

        if not default_profile:
            raise DefaultProfileError()
        stream_log.publish(
            tool_id,
            stream_log.log(
                stage=LogLevels.RUN,
                level=LogLevels.INFO,
                message=f"Invoking indexing for {tool_id}",
            ),
        )
        if not tool:
            logger.error(f"No tool instance found for the ID {tool_id}")
            raise ToolNotValid()

        stream_log.publish(
            tool_id,
            stream_log.log(
                stage=LogLevels.RUN,
                level=LogLevels.INFO,
                message=f"Calling prompt service for\
                      indexing the doc {file_name}",
            ),
        )
        logger.info(
            f"Invoking indexing in prompt service for the tool {tool_id}"
        )
        doc_id = PromptStudioHelper.dynamic_indexer(
            profile_manager=default_profile,
            tool_id=tool_id,
            file_path=file_path,
            org_id=org_id,
            document_id=document_id,
            is_summary=is_summary,
        )
        logger.info(f"Indexing done sucessfully for {file_name}")
        stream_log.publish(
            tool_id,
            stream_log.log(
                stage=LogLevels.RUN,
                level=LogLevels.INFO,
                message=f"Indexing successful for the file: {file_name}",
            ),
        )
        return doc_id

    @staticmethod
    def prompt_responder(
        tool_id: str,
        file_name: str,
        org_id: str,
        user_id: str,
        document_id: str,
        id: Optional[str] = None,
    ) -> Any:
        """Execute chain/single run of the prompts. Makes a call to prompt
        service and returns the dict of response.

        Args:
            id (Optional[str]): ID of the prompt
            tool_id (str): ID of tool created in prompt studio
            file_name (str): Name of the file uploaded
            org_id (str): Organization ID
            user_id (str): User's ID

        Raises:
            PromptNotValid: If a prompt could not be queried from the DB
            AnswerFetchError: Error from prompt-service

        Returns:
            Any: Dictionary containing the response from prompt-service
        """
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            org_id=org_id,
            user_id=user_id,
            tool_id=tool_id,
            is_create=False,
        )
        file_path = str(Path(file_path) / file_name)
        if id:
            message: str = f"Executing single prompt {id} of tool {tool_id}"
            logger.info(message)
            try:
                prompt_instance = PromptStudioHelper._fetch_prompt_from_id(id)
                prompts: list[ToolStudioPrompt] = []
                prompts.append(prompt_instance)
                tool: CustomTool = prompt_instance.tool_id

                if tool.summarize_as_source:
                    directory, filename = os.path.split(file_path)
                    file_path = os.path.join(
                        directory,
                        TSPKeys.SUMMARIZE,
                        os.path.splitext(filename)[0] + ".txt",
                    )

                stream_log.publish(
                    tool.tool_id,
                    stream_log.log(
                        stage=LogLevels.RUN,
                        level=LogLevels.INFO,
                        message=message,
                    ),
                )
                if not prompt_instance:
                    logger.error(f"Prompt id {id} does not have any data in db")
                    raise PromptNotValid()
            except Exception as exc:
                logger.error(f"Error while fetching prompt {exc}")
                raise AnswerFetchError()
            stream_log.publish(
                tool.tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Prompt instance fetched \
                        for {id} of tool {tool.tool_id}",
                ),
            )
            stream_log.publish(
                tool.tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Invoking prompt service for\
                          {id} of tool {tool.tool_id}",
                ),
            )
            logger.info(f"Invoking prompt service for prompt id {id}")
            response = PromptStudioHelper._fetch_response(
                path=file_path,
                tool=tool,
                prompts=prompts,
                org_id=org_id,
                document_id=document_id,
            )
            stream_log.publish(
                tool.tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Response fetched sucessfully \
                        from platform for prompt {id} of tool {tool.tool_id}",
                ),
            )
            logger.info(f"Response fetched succesfully for prompt {id}")
            return response
        else:
            message = f"Executing in single pass prompt mode for tool {tool_id}"
            logger.info(message)
            try:
                prompts = PromptStudioHelper.fetch_prompt_from_tool(tool_id)

                if not prompts:
                    raise NoPromptsFound()

                tool = prompts[0].tool_id
                response = PromptStudioHelper._fetch_single_pass_response(
                    file_path=file_path,
                    tool=tool,
                    prompts=prompts,
                    org_id=org_id,
                    document_id=document_id,
                )

                stream_log.publish(
                    tool_id,
                    stream_log.log(
                        stage=LogLevels.RUN,
                        level=LogLevels.INFO,
                        message="Executing single pass "
                        f"prompt for tool {tool_id}",
                    ),
                )
            except NoPromptsFound:
                logger.error("No prompts found for tool %s", tool_id)
                raise
            except Exception as e:
                logger.error("Error while fetching prompt %s", e)
                raise AnswerFetchError()
            stream_log.publish(
                tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Prompt instances fetched for tool {tool_id}",
                ),
            )
            stream_log.publish(
                tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Invoking prompt service for tool {tool_id}",
                ),
            )
            stream_log.publish(
                tool_id,
                stream_log.log(
                    stage=LogLevels.RUN,
                    level=LogLevels.INFO,
                    message=f"Response fetched sucessfully \
                        from platform for tool {tool_id}",
                ),
            )
            logger.info("Response fetched succesfully for tool %s", tool_id)
            return response

    @staticmethod
    def _fetch_response(
        tool: CustomTool,
        path: str,
        prompts: list[ToolStudioPrompt],
        org_id: str,
        document_id: str,
    ) -> Any:
        """Utility function to invoke prompt service. Used internally.

        Args:
            tool (CustomTool)
            path (str)
            prompt (dict)

        Raises:
            AnswerFetchError
        """
        monitor_llm_instance: Optional[AdapterInstance] = tool.monitor_llm
        monitor_llm: Optional[str] = None
        if monitor_llm_instance:
            monitor_llm = str(monitor_llm_instance.id)
        prompt_grammer = tool.prompt_grammer
        outputs: list[dict[str, Any]] = []
        grammer_dict = {}
        grammar_list = []

        # Using default profile manager llm if monitor_llm is None
        if monitor_llm:
            monitor_llm = str(monitor_llm_instance.id)
        else:
            # TODO: Use CustomTool model to get profile_manager
            profile_manager = ProfileManager.objects.get(
                prompt_studio_tool=tool, is_default=True
            )
            monitor_llm = str(profile_manager.llm.id)

        # Adding validations
        if prompt_grammer:
            for word, synonyms in prompt_grammer.items():
                synonyms = prompt_grammer[word]
                grammer_dict[TSPKeys.WORD] = word
                grammer_dict[TSPKeys.SYNONYMS] = synonyms
                grammar_list.append(grammer_dict)
                grammer_dict = {}
        for prompt in prompts:
            # Need to check the user who created profile manager
            # has access to adapters
            PromptStudioHelper.validate_profile_manager_owner_access(
                prompt.profile_manager
            )
            # Not checking reindex here as there might be
            # change in Profile Manager
            vector_db = str(prompt.profile_manager.vector_store.id)
            embedding_model = str(prompt.profile_manager.embedding_model.id)
            llm = str(prompt.profile_manager.llm.id)
            x2text = str(prompt.profile_manager.x2text.id)
            prompt_profile_manager: ProfileManager = prompt.profile_manager
            if not prompt_profile_manager:
                raise DefaultProfileError()
            PromptStudioHelper.dynamic_indexer(
                profile_manager=prompt_profile_manager,
                file_path=path,
                tool_id=str(tool.tool_id),
                org_id=org_id,
                document_id=document_id,
                is_summary=tool.summarize_as_source,
            )

            output: dict[str, Any] = {}
            output[TSPKeys.ASSERTION_FAILURE_PROMPT] = (
                prompt.assertion_failure_prompt
            )
            output[TSPKeys.ASSERT_PROMPT] = prompt.assert_prompt
            output[TSPKeys.IS_ASSERT] = prompt.is_assert
            output[TSPKeys.PROMPT] = prompt.prompt
            output[TSPKeys.ACTIVE] = prompt.active
            output[TSPKeys.CHUNK_SIZE] = prompt.profile_manager.chunk_size
            output[TSPKeys.VECTOR_DB] = vector_db
            output[TSPKeys.EMBEDDING] = embedding_model
            output[TSPKeys.CHUNK_OVERLAP] = prompt.profile_manager.chunk_overlap
            output[TSPKeys.LLM] = llm
            output[TSPKeys.PREAMBLE] = tool.preamble
            output[TSPKeys.POSTAMBLE] = tool.postamble
            output[TSPKeys.GRAMMAR] = grammar_list
            output[TSPKeys.TYPE] = prompt.enforce_type
            output[TSPKeys.NAME] = prompt.prompt_key
            output[TSPKeys.RETRIEVAL_STRATEGY] = (
                prompt.profile_manager.retrieval_strategy
            )
            output[TSPKeys.SIMILARITY_TOP_K] = (
                prompt.profile_manager.similarity_top_k
            )
            output[TSPKeys.SECTION] = prompt.profile_manager.section
            output[TSPKeys.X2TEXT_ADAPTER] = x2text

            # Eval settings for the prompt
            output[TSPKeys.EVAL_SETTINGS] = {}
            output[TSPKeys.EVAL_SETTINGS][
                TSPKeys.EVAL_SETTINGS_EVALUATE
            ] = prompt.evaluate
            output[TSPKeys.EVAL_SETTINGS][TSPKeys.EVAL_SETTINGS_MONITOR_LLM] = [
                monitor_llm
            ]
            output[TSPKeys.EVAL_SETTINGS][
                TSPKeys.EVAL_SETTINGS_EXCLUDE_FAILED
            ] = tool.exclude_failed
            for attr in dir(prompt):
                if attr.startswith(TSPKeys.EVAL_METRIC_PREFIX):
                    attr_val = getattr(prompt, attr)
                    output[TSPKeys.EVAL_SETTINGS][attr] = attr_val

            outputs.append(output)

        tool_id = str(tool.tool_id)

        file_hash = ToolUtils.get_hash_from_file(file_path=path)

        payload = {
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.FILE_NAME: path,
            TSPKeys.FILE_HASH: file_hash,
        }

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        responder = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
        )

        answer = responder.answer_prompt(payload)
        # TODO: Make use of dataclasses
        if answer["status"] == "ERROR":
            raise AnswerFetchError()
        output_response = json.loads(answer["structure_output"])
        return output_response

    @staticmethod
    def dynamic_indexer(
        profile_manager: ProfileManager,
        tool_id: str,
        file_path: str,
        org_id: str,
        document_id: str,
        is_summary: bool = False,
    ) -> str:
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

        Returns:
            str: Index key for the combination of arguments
        """
        try:
            util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
            tool_index = ToolIndex(tool=util)
        except Exception as e:
            logger.error(f"Error while instatiating SDKs {e}")
            raise IndexingError()
        embedding_model = str(profile_manager.embedding_model.id)
        vector_db = str(profile_manager.vector_store.id)
        x2text_adapter = str(profile_manager.x2text.id)
        file_hash = ToolUtils.get_hash_from_file(file_path=file_path)
        extract_file_path: Optional[str] = None
        if not is_summary:
            directory, filename = os.path.split(file_path)
            extract_file_path = os.path.join(
                directory, "extract", os.path.splitext(filename)[0] + ".txt"
            )
        else:
            profile_manager.chunk_size = 0
        try:
            doc_id: str = tool_index.index_file(
                tool_id=tool_id,
                embedding_type=embedding_model,
                vector_db=vector_db,
                x2text_adapter=x2text_adapter,
                file_path=file_path,
                file_hash=file_hash,
                chunk_size=profile_manager.chunk_size,
                chunk_overlap=profile_manager.chunk_overlap,
                reindex=profile_manager.reindex,
                output_file_path=extract_file_path,
            )

            PromptStudioIndexHelper.handle_index_manager(
                document_id=document_id,
                is_summary=is_summary,
                profile_manager=profile_manager,
                doc_id=doc_id,
            )
            return doc_id
        except SdkError as e:
            raise IndexingError(str(e))

    @staticmethod
    def _fetch_single_pass_response(
        tool: CustomTool,
        file_path: str,
        prompts: list[ToolStudioPrompt],
        org_id: str,
        document_id: str,
    ) -> Any:
        tool_id: str = str(tool.tool_id)
        outputs: list[dict[str, Any]] = []
        grammar: list[dict[str, Any]] = []
        prompt_grammar = tool.prompt_grammer
        default_profile: ProfileManager = ProfileManager.objects.get(
            prompt_studio_tool=tool, is_default=True
        )
        default_profile.chunk_size = 0  # To retrive full context

        if prompt_grammar:
            for word, synonyms in prompt_grammar.items():
                grammar.append({TSPKeys.WORD: word, TSPKeys.SYNONYMS: synonyms})

        if not default_profile:
            raise DefaultProfileError()

        PromptStudioHelper.dynamic_indexer(
            profile_manager=default_profile,
            file_path=file_path,
            tool_id=tool_id,
            org_id=org_id,
            is_summary=tool.summarize_as_source,
            document_id=document_id,
        )

        vector_db = str(default_profile.vector_store.id)
        embedding_model = str(default_profile.embedding_model.id)
        llm = str(default_profile.llm.id)
        x2text = str(default_profile.x2text.id)
        llm_profile_manager = {}
        llm_profile_manager[TSPKeys.PREAMBLE] = tool.preamble
        llm_profile_manager[TSPKeys.POSTAMBLE] = tool.postamble
        llm_profile_manager[TSPKeys.GRAMMAR] = grammar
        llm_profile_manager[TSPKeys.LLM] = llm
        llm_profile_manager[TSPKeys.X2TEXT_ADAPTER] = x2text
        llm_profile_manager[TSPKeys.VECTOR_DB] = vector_db
        llm_profile_manager[TSPKeys.EMBEDDING] = embedding_model
        llm_profile_manager[TSPKeys.CHUNK_SIZE] = default_profile.chunk_size
        llm_profile_manager[TSPKeys.CHUNK_OVERLAP] = (
            default_profile.chunk_overlap
        )

        for prompt in prompts:
            output: dict[str, Any] = {}
            output[TSPKeys.PROMPT] = prompt.prompt
            output[TSPKeys.ACTIVE] = prompt.active
            output[TSPKeys.TYPE] = prompt.enforce_type
            output[TSPKeys.NAME] = prompt.prompt_key
            outputs.append(output)

        if tool.summarize_as_source:
            path = Path(file_path)
            file_path = str(
                path.parent / TSPKeys.SUMMARIZE / (path.stem + ".txt")
            )
        file_hash = ToolUtils.get_hash_from_file(file_path=file_path)

        payload = {
            TSPKeys.LLM_PROFILE_MANAGER: llm_profile_manager,
            TSPKeys.OUTPUTS: outputs,
            TSPKeys.TOOL_ID: tool_id,
            TSPKeys.FILE_HASH: file_hash,
        }

        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)

        responder = PromptTool(
            tool=util,
            prompt_host=settings.PROMPT_HOST,
            prompt_port=settings.PROMPT_PORT,
        )

        answer = responder.single_pass_extraction(payload)
        # TODO: Make use of dataclasses
        if answer["status"] == "ERROR":
            raise AnswerFetchError()
        output_response = json.loads(answer["structure_output"])
        return output_response
