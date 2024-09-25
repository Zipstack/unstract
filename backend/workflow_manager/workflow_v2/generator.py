import logging
import uuid
from typing import Any

from rest_framework.request import Request
from tool_instance_v2.constants import ToolInstanceKey as TIKey
from tool_instance_v2.exceptions import ToolInstantiationError
from tool_instance_v2.tool_processor import ToolProcessor
from unstract.tool_registry.dto import Tool
from workflow_manager.workflow_v2.constants import WorkflowKey
from workflow_manager.workflow_v2.dto import ProvisionalWorkflow
from workflow_manager.workflow_v2.exceptions import WorkflowGenerationError
from workflow_manager.workflow_v2.models.workflow import Workflow as WorkflowModel

from unstract.core.llm_workflow_generator.llm_interface import LLMInterface

logger = logging.getLogger(__name__)


# TODO: Can be removed as not getting used with UX chnages.
class WorkflowGenerator:
    """Helps with generating a workflow using the LLM."""

    def __init__(self, workflow_id: str = str(uuid.uuid4())) -> None:
        self._request: Request = {}
        self._llm_response = ""
        self._workflow_id = workflow_id
        self._provisional_wf: ProvisionalWorkflow

    @property
    def llm_response(self) -> dict[str, Any]:
        output: dict[str, str] = self._provisional_wf.output
        return output

    @property
    def provisional_wf(self) -> ProvisionalWorkflow:
        return self._provisional_wf

    def _get_provisional_workflow(self, tools: list[Tool]) -> ProvisionalWorkflow:
        """Helper to generate the provisional workflow Gets stored as
        `workflow.Workflow.llm_response` eventually."""
        provisional_wf: ProvisionalWorkflow
        try:
            if not self._request:
                raise WorkflowGenerationError(
                    "Unable to generate a workflow: missing request"
                )
            llm_interface = LLMInterface()

            provisional_wf_dict = llm_interface.get_provisional_workflow_from_llm(
                workflow_id=self._workflow_id,
                tools=tools,
                user_prompt=self._request.data.get(WorkflowKey.PROMPT_TEXT),
                use_cache=True,
            )
            provisional_wf = ProvisionalWorkflow(provisional_wf_dict)
            if provisional_wf.result != "OK":
                raise WorkflowGenerationError(
                    f"Unable to generate a workflow: {provisional_wf.output}"
                )
        except Exception as e:
            logger.error(f"{e}")
            raise WorkflowGenerationError
        return provisional_wf

    def set_request(self, request: Request) -> None:
        self._request = request

    def generate_workflow(self, tools: list[Tool]) -> None:
        """Used to talk to the GPT model through core and obtain a provisional
        workflow for the user to work with."""
        self._provisional_wf = self._get_provisional_workflow(tools)

    @staticmethod
    def get_tool_instance_data_from_llm(
        workflow: WorkflowModel,
    ) -> list[dict[str, str]]:
        """Used to generate the dict of tool instances for a given workflow.

        Call with ToolInstanceSerializer(data=tool_instance_data_list,many=True)
        """
        tool_instance_data_list = []
        for step, tool_step in enumerate(
            workflow.llm_response.get(WorkflowKey.WF_STEPS, [])
        ):
            step = step + 1
            logger.info(f"Building tool instance data for step: {step}")
            tool_function: str = tool_step[WorkflowKey.WF_TOOL]
            wf_input: str = tool_step[WorkflowKey.WF_INPUT]
            wf_output: str = tool_step[WorkflowKey.WF_OUTPUT]
            try:
                tool: Tool = ToolProcessor.get_tool_by_uid(tool_function)
                # TODO: Mark optional fields in model and handle in ToolInstance serializer  # noqa
                tool_instance_data = {
                    TIKey.PK: tool_step[WorkflowKey.WF_TOOL_UUID],
                    TIKey.WORKFLOW: workflow.id,
                    # Added to support changes for UN-154
                    WorkflowKey.WF_ID: workflow.id,
                    TIKey.TOOL_ID: tool_function,
                    TIKey.METADATA: {
                        WorkflowKey.WF_TOOL_INSTANCE_ID: tool_step[
                            WorkflowKey.WF_TOOL_UUID
                        ],
                        **ToolProcessor.get_default_settings(tool),
                    },
                    TIKey.STEP: str(step),
                    TIKey.INPUT: wf_input,
                    TIKey.OUTPUT: wf_output,
                }
                tool_instance_data_list.append(tool_instance_data)
            except Exception as e:
                logger.error(f"Error while getting data for {tool_function}: {e}")
                raise ToolInstantiationError(tool_name=tool_function)
        return tool_instance_data_list
