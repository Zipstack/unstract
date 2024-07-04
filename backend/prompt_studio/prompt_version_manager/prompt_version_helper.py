import logging

from adapter_processor.constants import AdapterKeys
from adapter_processor.models import AdapterInstance
from django.db.models.manager import BaseManager
from prompt_studio.prompt_profile_manager.models import ProfileManager
from prompt_studio.prompt_studio_core.models import CustomTool

CHOICES_JSON = "/static/select_choices.json"
ERROR_MSG = "User %s doesn't have access to adapter %s"

logger = logging.getLogger(__name__)


class PromptStudioHelper:
    """Helper class for Custom tool operations."""

    @staticmethod
    def create_prompt_version(tool_id: str, prompt_id: str) -> None:
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
                created_by="",
                modified_by="",
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

    # @staticmethod
    # def _publish_log(
    #     component: dict[str, str], level: str, state: str, message: str
    # ) -> None:
    #     LogPublisher.publish(
    #         StateStore.get(Common.LOG_EVENTS_ID),
    #         LogPublisher.log_prompt(component, level, state, message),
    #     )

    # @staticmethod
    # def get_select_fields() -> dict[str, Any]:
    #     """Method to fetch dropdown field values for frontend.

    #     Returns:
    #         dict[str, Any]: Dict for dropdown data
    #     """
    #     f = open(f"{os.path.dirname(__file__)}{CHOICES_JSON}")
    #     choices = f.read()
    #     f.close()
    #     response: dict[str, Any] = json.loads(choices)
    #     return response

    # @staticmethod
    # def _fetch_prompt_from_id(id: str) -> ToolStudioPrompt:
    #     """Internal function used to fetch prompt from ID.

    #     Args:
    #         id (_type_): UUID of the prompt

    #     Returns:
    #         ToolStudioPrompt: Instance of the model
    #     """
    #     prompt_instance: ToolStudioPrompt = ToolStudioPrompt.objects.get(pk=id)
    #     return prompt_instance

    # @staticmethod
    # def fetch_prompt_versions(tool_id: str, prompt_id: str) -> list[ToolStudioPrompt]:
    #     """Internal function used to fetch mapped prompts from ToolID.

    #     Args:
    #         tool_id (_type_): UUID of the tool

    #     Returns:
    #         List[ToolStudioPrompt]: List of instance of the model
    #     """
    #     prompt_instances: list[ToolStudioPrompt] = ToolStudioPrompt.objects.filter(
    #         tool_id=tool_id
    #     ).order_by(TSPKeys.SEQUENCE_NUMBER)
    #     return prompt_instances
