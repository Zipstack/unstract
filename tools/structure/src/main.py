import datetime
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from constants import SettingsKeys  # type: ignore [attr-defined]
from helpers import StructureToolHelper as STHelper
from utils import json_to_markdown

from unstract.sdk.constants import LogState, MetadataKey, ToolEnv, UsageKwargs
from unstract.sdk.platform import PlatformHelper
from unstract.sdk.prompt import PromptTool
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint

logger = logging.getLogger(__name__)

PAID_FEATURE_MSG = (
    "It is a cloud / enterprise feature. If you have purchased a plan and still "
    "face this issue, please contact support"
)


class StructureTool(BaseTool):
    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        enable_challenge: bool = settings.get(SettingsKeys.ENABLE_CHALLENGE, False)
        challenge_llm: str = settings.get(SettingsKeys.CHALLENGE_LLM_ADAPTER_ID, "")
        if enable_challenge and not challenge_llm:
            raise ValueError("Challenge LLM is not set after enabling Challenge")

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        prompt_registry_id: str = settings[SettingsKeys.PROMPT_REGISTRY_ID]
        is_challenge_enabled: bool = settings.get(SettingsKeys.ENABLE_CHALLENGE, False)
        is_summarization_enabled: bool = settings.get(
            SettingsKeys.SUMMARIZE_AS_SOURCE, False
        )
        is_single_pass_enabled: bool = settings.get(
            SettingsKeys.SINGLE_PASS_EXTRACTION_MODE, False
        )
        challenge_llm: str = settings.get(SettingsKeys.CHALLENGE_LLM_ADAPTER_ID, "")
        is_highlight_enabled: bool = settings.get(SettingsKeys.ENABLE_HIGHLIGHT, False)
        responder: PromptTool = PromptTool(
            tool=self,
            prompt_port=self.get_env_or_die(SettingsKeys.PROMPT_PORT),
            prompt_host=self.get_env_or_die(SettingsKeys.PROMPT_HOST),
            request_id=self.file_execution_id,
        )
        self.stream_log(
            f"Fetching prompt studio exported tool with UUID '{prompt_registry_id}'"
        )
        try:
            platform_helper: PlatformHelper = PlatformHelper(
                tool=self,
                platform_port=self.get_env_or_die(ToolEnv.PLATFORM_PORT),
                platform_host=self.get_env_or_die(ToolEnv.PLATFORM_HOST),
                request_id=self.file_execution_id,
            )
            exported_tool = platform_helper.get_prompt_studio_tool(
                prompt_registry_id=prompt_registry_id
            )
            tool_metadata = exported_tool[SettingsKeys.TOOL_METADATA]
            ps_project_name = tool_metadata.get("name", prompt_registry_id)
            # Count only the active (enabled) prompts
            total_prompt_count = len(tool_metadata[SettingsKeys.OUTPUTS])
            self.stream_log(
                f"Retrieved prompt studio exported tool '{ps_project_name}' having "
                f"'{total_prompt_count}' prompts"
            )
        except Exception as e:
            self.stream_error_and_exit(f"Error fetching prompt studio project: {e}")

        active_prompt_count = len(
            [
                output
                for output in tool_metadata[SettingsKeys.OUTPUTS]
                if output.get("active", False)
            ]
        )
        # Update GUI
        input_log = f"## Loaded '{ps_project_name}'\n{json_to_markdown(tool_metadata)}\n"
        output_log = (
            f"## Processing '{self.source_file_name}'\nThis might take a while and "
            "involve...\n- Extracting text\n- Indexing\n- Retrieving answers "
            f"for '{active_prompt_count}' prompts"
        )
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        file_hash = self.get_exec_metadata.get(MetadataKey.SOURCE_HASH)
        tool_id = tool_metadata[SettingsKeys.TOOL_ID]
        tool_settings = tool_metadata[SettingsKeys.TOOL_SETTINGS]
        outputs = tool_metadata[SettingsKeys.OUTPUTS]
        tool_settings[SettingsKeys.CHALLENGE_LLM] = challenge_llm
        tool_settings[SettingsKeys.ENABLE_CHALLENGE] = is_challenge_enabled
        tool_settings[SettingsKeys.ENABLE_SINGLE_PASS_EXTRACTION] = is_single_pass_enabled
        tool_settings[SettingsKeys.SUMMARIZE_AS_SOURCE] = is_summarization_enabled
        tool_settings[SettingsKeys.ENABLE_HIGHLIGHT] = is_highlight_enabled
        _, file_name = os.path.split(input_file)
        if is_summarization_enabled:
            file_name = SettingsKeys.SUMMARIZE
        tool_data_dir = Path(self.get_env_or_die(ToolEnv.EXECUTION_DATA_DIR))
        execution_run_data_folder = Path(self.get_env_or_die(ToolEnv.EXECUTION_DATA_DIR))

        extracted_input_file = str(execution_run_data_folder / SettingsKeys.EXTRACT)
        # Resolve and pass log events ID
        payload = {
            SettingsKeys.RUN_ID: self.file_execution_id,
            SettingsKeys.EXECUTION_ID: self.execution_id,
            SettingsKeys.TOOL_SETTINGS: tool_settings,
            SettingsKeys.OUTPUTS: outputs,
            SettingsKeys.TOOL_ID: tool_id,
            SettingsKeys.FILE_HASH: file_hash,
            SettingsKeys.FILE_NAME: file_name,
            SettingsKeys.FILE_PATH: extracted_input_file,
            SettingsKeys.EXECUTION_SOURCE: SettingsKeys.TOOL,
        }
        self.stream_log(f"Extracting document '{self.source_file_name}'")
        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[UsageKwargs.RUN_ID] = self.file_execution_id
        usage_kwargs[UsageKwargs.FILE_NAME] = self.source_file_name
        usage_kwargs[UsageKwargs.EXECUTION_ID] = self.execution_id
        extracted_text = STHelper.dynamic_extraction(
            file_path=input_file,
            enable_highlight=is_highlight_enabled,
            usage_kwargs=usage_kwargs,
            run_id=self.file_execution_id,
            tool_settings=tool_settings,
            extract_file_path=tool_data_dir / SettingsKeys.EXTRACT,
            tool=self,
            execution_run_data_folder=str(execution_run_data_folder),
        )

        index_metrics = {}
        if is_summarization_enabled:
            summarize_file_path, summarize_file_hash = self._summarize(
                tool_settings=tool_settings,
                tool_data_dir=tool_data_dir,
                responder=responder,
                outputs=outputs,
                usage_kwargs=usage_kwargs,
            )
            payload[SettingsKeys.FILE_HASH] = summarize_file_hash
            payload[SettingsKeys.FILE_PATH] = summarize_file_path
        elif not is_single_pass_enabled:
            # Track seen parameter combinations to avoid duplicate indexing
            seen_params = set()

            for output in outputs:
                # Get current parameter combination
                chunk_size = output[SettingsKeys.CHUNK_SIZE]
                chunk_overlap = output[SettingsKeys.CHUNK_OVERLAP]
                vector_db = tool_settings[SettingsKeys.VECTOR_DB]
                embedding = tool_settings[SettingsKeys.EMBEDDING]
                x2text = tool_settings[SettingsKeys.X2TEXT_ADAPTER]

                # Create a unique key for this parameter combination
                param_key = (
                    f"chunk_size={chunk_size}_"
                    f"chunk_overlap={chunk_overlap}_"
                    f"vector_db={vector_db}_"
                    f"embedding={embedding}_"
                    f"x2text={x2text}"
                )

                # Only process if we haven't seen this combination yet and chunk_size is not zero
                if chunk_size != 0 and param_key not in seen_params:
                    seen_params.add(param_key)

                    indexing_start_time = datetime.datetime.now()
                    self.stream_log(
                        f"Indexing document with: chunk_size={chunk_size}, "
                        f"chunk_overlap={chunk_overlap}, vector_db={vector_db}, "
                        f"embedding={embedding}, x2text={x2text}"
                    )

                    STHelper.dynamic_indexing(
                        tool_settings=tool_settings,
                        run_id=self.file_execution_id,
                        file_path=tool_data_dir / SettingsKeys.EXTRACT,
                        tool=self,
                        execution_run_data_folder=str(execution_run_data_folder),
                        chunk_overlap=chunk_overlap,
                        reindex=True,
                        usage_kwargs=usage_kwargs,
                        enable_highlight=is_highlight_enabled,
                        chunk_size=chunk_size,
                        tool_id=tool_metadata[SettingsKeys.TOOL_ID],
                        file_hash=file_hash,
                        extracted_text=extracted_text,
                    )

                    index_metrics[output[SettingsKeys.NAME]] = {
                        SettingsKeys.INDEXING: {
                            "time_taken(s)": STHelper.elapsed_time(
                                start_time=indexing_start_time
                            )
                        }
                    }

        if is_single_pass_enabled:
            self.stream_log("Fetching response for single pass extraction...")
            structured_output = responder.single_pass_extraction(
                payload=payload,
            )
        else:
            for output in outputs:
                if SettingsKeys.TABLE_SETTINGS in output:
                    table_settings = output[SettingsKeys.TABLE_SETTINGS]
                    is_directory_mode: bool = table_settings.get(
                        SettingsKeys.IS_DIRECTORY_MODE, False
                    )
                    table_settings[SettingsKeys.INPUT_FILE] = extracted_input_file
                    table_settings[SettingsKeys.IS_DIRECTORY_MODE] = is_directory_mode
                    self.stream_log(f"Performing table extraction with: {table_settings}")
                    output.update({SettingsKeys.TABLE_SETTINGS: table_settings})

            self.stream_log(f"Fetching responses for '{len(outputs)}' prompt(s)...")
            structured_output = responder.answer_prompt(
                payload=payload,
            )

        # HACK: Replacing actual file's name instead of INFILE
        if SettingsKeys.METADATA in structured_output:
            structured_output[SettingsKeys.METADATA][SettingsKeys.FILE_NAME] = (
                self.source_file_name
            )

        if merged_metrics := self._merge_metrics(
            structured_output.get(SettingsKeys.METRICS, {}), index_metrics
        ):
            structured_output[SettingsKeys.METRICS] = merged_metrics
        # Update GUI
        output_log = (
            f"## Result\n**NOTE:** In case of a deployed pipeline, the result would "
            "be a JSON. This has been rendered for readability here\n"
            f"{json_to_markdown(structured_output)}\n"
        )
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        try:
            self.stream_log(
                "Writing prompt studio project's output to workflow's storage"
            )
            output_path = Path(output_dir) / f"{Path(self.source_file_name).stem}.json"
            self.workflow_filestorage.json_dump(path=output_path, data=structured_output)
            self.stream_log(
                "Prompt studio project's output written successfully to workflow's storage"
            )
        except OSError as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")
        except json.JSONDecodeError as e:
            self.stream_error_and_exit(f"Error encoding JSON: {e}")
        self.write_tool_result(data=structured_output)

    def _merge_metrics(self, metrics1: dict, metrics2: dict) -> dict:
        """Intelligently merge two metrics dictionaries.

        For keys that exist in both dictionaries with dictionary values, merge the dictionaries.
        For keys that exist in only one dictionary or have non-dictionary values, use the value as-is.

        Args:
            metrics1 (dict): First metrics dictionary
            metrics2 (dict): Second metrics dictionary

        Returns:
            dict: Merged metrics dictionary
        """
        merged_metrics = {}

        # Get all unique keys from both dictionaries
        all_keys = set(metrics1) | set(metrics2)

        for key in all_keys:
            # If key exists in both dictionaries and both values are dictionaries, merge them
            if (
                key in metrics1
                and key in metrics2
                and isinstance(metrics1[key], dict)
                and isinstance(metrics2[key], dict)
            ):
                merged_metrics[key] = {**metrics1[key], **metrics2[key]}
            # Otherwise just take the value from whichever dictionary has it
            elif key in metrics1:
                merged_metrics[key] = metrics1[key]
            else:
                merged_metrics[key] = metrics2[key]

        return merged_metrics

    def _summarize(
        self,
        tool_settings: dict[str, Any],
        tool_data_dir: Path,
        responder: PromptTool,
        outputs: dict[str, Any],
        usage_kwargs: dict[Any, Any] = {},
    ) -> tuple[str, str]:
        """Summarizes the context of the file.

        Args:
            tool_settings (dict[str, Any]): Settings for the tool.
            tool_data_dir (Path): Directory where tool data is stored.
            responder (PromptTool): Instance of a tool used to generate the summary.
            outputs (dict[str, Any]): Dictionary containing prompt details.
            usage_kwargs (dict[Any, Any]): Used to capture usage metrics.

        Returns:
            tuple[str, str]: Tuple containing the path to the summarized file and its hash.
        """
        llm_adapter_instance_id: str = tool_settings[SettingsKeys.LLM]
        embedding_instance_id: str = tool_settings[SettingsKeys.EMBEDDING]
        vector_db_instance_id: str = tool_settings[SettingsKeys.VECTOR_DB]
        x2text_instance_id: str = tool_settings[SettingsKeys.X2TEXT_ADAPTER]
        summarize_prompt: str = tool_settings[SettingsKeys.SUMMARIZE_PROMPT]
        run_id: str = usage_kwargs.get(UsageKwargs.RUN_ID)
        extract_file_path = tool_data_dir / SettingsKeys.EXTRACT
        summarize_file_path = tool_data_dir / SettingsKeys.SUMMARIZE

        summarized_context = ""
        self.stream_log(
            f"Checking if summarized context exists at '{summarize_file_path}'..."
        )
        if self.workflow_filestorage.exists(summarize_file_path):
            summarized_context = self.workflow_filestorage.read(
                path=summarize_file_path, mode="r"
            )
        if not summarized_context:
            context = ""
            context = self.workflow_filestorage.read(path=extract_file_path, mode="r")
            prompt_keys = []
            for output in outputs:
                prompt_keys.append(output[SettingsKeys.NAME])
                output[SettingsKeys.EMBEDDING] = embedding_instance_id
                output[SettingsKeys.VECTOR_DB] = vector_db_instance_id
                output[SettingsKeys.X2TEXT_ADAPTER] = x2text_instance_id
                output[SettingsKeys.CHUNK_SIZE] = 0
                output[SettingsKeys.CHUNK_OVERLAP] = 0
            self.stream_log("Summarized context not found, summarizing...")
            payload = {
                SettingsKeys.RUN_ID: run_id,
                SettingsKeys.LLM_ADAPTER_INSTANCE_ID: llm_adapter_instance_id,
                SettingsKeys.SUMMARIZE_PROMPT: summarize_prompt,
                SettingsKeys.CONTEXT: context,
                SettingsKeys.PROMPT_KEYS: prompt_keys,
            }
            structure_output = responder.summarize(payload=payload)
            summarized_context = structure_output.get(SettingsKeys.DATA, "")
            self.stream_log(f"Writing summarized context to '{summarize_file_path}'")
            self.workflow_filestorage.write(
                path=summarize_file_path, mode="w", data=summarized_context
            )

        summarize_file_hash: str = self.workflow_filestorage.get_hash_from_file(
            path=summarize_file_path
        )
        return str(summarize_file_path), summarize_file_hash


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = StructureTool.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
