import json
import os
import sys
from pathlib import Path
from typing import Any

from constants import SettingsKeys  # type: ignore [attr-defined]
from unstract.sdk.constants import LogState, MetadataKey
from unstract.sdk.index import Index
from unstract.sdk.prompt import PromptTool
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint
from unstract.sdk.utils import ToolUtils
from unstract.sdk.utils.common_utils import CommonUtils


class StructureTool(BaseTool):
    def validate(self, input_file: str, settings: dict[str, Any]) -> None:
        pass

    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        prompt_registry_id: str = settings[SettingsKeys.PROMPT_REGISTRY_ID]
        challenge_llm: str = settings[SettingsKeys.CHALLENGE_LLM_ADAPTER_ID]
        enable_challenge: bool = settings[SettingsKeys.ENABLE_CHALLENGE]

        summarize_as_source: bool = settings[SettingsKeys.SUMMARIZE_AS_SOURCE]
        single_pass_extraction_mode: bool = settings[
            SettingsKeys.SINGLE_PASS_EXTRACTION_MODE
        ]
        responder: PromptTool = PromptTool(
            tool=self,
            prompt_port=self.get_env_or_die(SettingsKeys.PROMPT_PORT),
            prompt_host=self.get_env_or_die(SettingsKeys.PROMPT_HOST),
        )
        self.stream_log(f"Fetching metadata for tool {prompt_registry_id}")
        try:
            exported_tool = responder.get_exported_tool(
                tool=self, prompt_registry_id=prompt_registry_id
            )
            tool_metadata = exported_tool[SettingsKeys.TOOL_METADATA]
            self.stream_log(f"Tool Metadata retrived succesfully: {tool_metadata}")
        except Exception as e:
            self.stream_error_and_exit(f"Error loading structure definition: {e}")

        # Update GUI
        input_log = f"### Structure Definition:\n```json\n{tool_metadata}\n```\n\n"
        output_log = "### Indexing..."
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        file_hash = self.get_exec_metadata.get(MetadataKey.SOURCE_HASH)
        index = Index(tool=self)
        tool_id = tool_metadata[SettingsKeys.TOOL_ID]
        tool_settings = tool_metadata[SettingsKeys.TOOL_SETTINGS]
        outputs = tool_metadata[SettingsKeys.OUTPUTS]
        enable_highlight: bool = tool_settings.get(SettingsKeys.ENABLE_HIGHLIGHT, False)
        tool_settings[SettingsKeys.CHALLENGE_LLM] = challenge_llm
        tool_settings[SettingsKeys.ENABLE_CHALLENGE] = enable_challenge
        tool_settings[SettingsKeys.ENABLE_SINGLE_PASS_EXTRACTION] = (
            single_pass_extraction_mode
        )

        prompt_service_resp = None
        _, file_name = os.path.split(input_file)
        if summarize_as_source:
            file_name = SettingsKeys.SUMMARIZE
        tool_data_dir = Path(self.get_env_or_die(SettingsKeys.TOOL_DATA_DIR))
        run_id = CommonUtils.generate_uuid()
        # TODO : Resolve and pass log events ID
        payload = {
            SettingsKeys.RUN_ID: run_id,
            SettingsKeys.TOOL_SETTINGS: tool_settings,
            SettingsKeys.OUTPUTS: outputs,
            SettingsKeys.TOOL_ID: tool_id,
            SettingsKeys.FILE_HASH: file_hash,
            SettingsKeys.FILE_NAME: file_name,
        }

        # TODO: Need to split extraction and indexing
        # to avoid unwanted indexing
        self.stream_log("Indexing document")
        usage_kwargs: dict[Any, Any] = dict()
        usage_kwargs[SettingsKeys.RUN_ID] = run_id
        if tool_settings[SettingsKeys.ENABLE_SINGLE_PASS_EXTRACTION]:
            index.index(
                tool_id=tool_id,
                embedding_instance_id=tool_settings[SettingsKeys.EMBEDDING],
                vector_db_instance_id=tool_settings[SettingsKeys.VECTOR_DB],
                x2text_instance_id=tool_settings[SettingsKeys.X2TEXT_ADAPTER],
                file_path=input_file,
                file_hash=file_hash,
                chunk_size=tool_settings[SettingsKeys.CHUNK_SIZE],
                chunk_overlap=tool_settings[SettingsKeys.CHUNK_OVERLAP],
                output_file_path=tool_data_dir / SettingsKeys.EXTRACT,
                reindex=True,
                usage_kwargs=usage_kwargs,
                enable_highlight=enable_highlight,
            )
            if summarize_as_source:
                summarize_file_hash = self._summarize_and_index(
                    tool_id=tool_id,
                    tool_settings=tool_settings,
                    tool_data_dir=tool_data_dir,
                    responder=responder,
                    outputs=outputs,
                    index=index,
                    usage_kwargs=usage_kwargs,
                    enable_highlight=enable_highlight,
                )
                payload[SettingsKeys.FILE_HASH] = summarize_file_hash
            self.stream_log("Fetching response for single pass extraction")
            prompt_service_resp = responder.single_pass_extraction(payload=payload)
        else:
            try:
                # To reindex even if file is already
                # indexed to get the output in required path
                reindex = True
                for output in outputs:
                    if reindex or not summarize_as_source:
                        index.index(
                            tool_id=tool_metadata[SettingsKeys.TOOL_ID],
                            embedding_instance_id=output[SettingsKeys.EMBEDDING],
                            vector_db_instance_id=output[SettingsKeys.VECTOR_DB],
                            x2text_instance_id=output[SettingsKeys.X2TEXT_ADAPTER],
                            file_path=input_file,
                            file_hash=file_hash,
                            chunk_size=output[SettingsKeys.CHUNK_SIZE],
                            chunk_overlap=output[SettingsKeys.CHUNK_OVERLAP],
                            output_file_path=tool_data_dir / SettingsKeys.EXTRACT,
                            reindex=reindex,
                            usage_kwargs=usage_kwargs,
                            enable_highlight=enable_highlight,
                        )

                    if summarize_as_source:
                        summarize_file_hash = self._summarize_and_index(
                            tool_id=tool_id,
                            tool_settings=tool_settings,
                            tool_data_dir=tool_data_dir,
                            responder=responder,
                            outputs=outputs,
                            index=index,
                            usage_kwargs=usage_kwargs,
                        )
                        payload[SettingsKeys.OUTPUTS] = outputs
                        payload[SettingsKeys.FILE_HASH] = summarize_file_hash
                        break
                    reindex = False
            except Exception as e:
                self.stream_error_and_exit(f"Error fetching data and indexing: {e}")
            self.stream_log("Fetching responses for prompts...")
            prompt_service_resp = responder.answer_prompt(payload=payload)

        # TODO: Make use of dataclasses
        if prompt_service_resp[SettingsKeys.STATUS] != SettingsKeys.OK:
            self.stream_error_and_exit(
                f"Failed to fetch responses for "
                f"prompts: {prompt_service_resp[SettingsKeys.ERROR]}"
            )

        structured_output = prompt_service_resp[SettingsKeys.STRUCTURE_OUTPUT]

        # Update GUI
        input_log = (
            f"### Structure Definition:\n"
            f"```json\n{json.dumps(tool_metadata, indent=2)}\n```\n\n"
        )
        output_log = f"### Parsed output:\n```json\n{structured_output}\n```\n\n"
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        # Write the translated text to output file
        try:
            self.stream_log("Writing parsed output...")
            source_name = self.get_exec_metadata.get(MetadataKey.SOURCE_NAME)
            output_path = Path(output_dir) / f"{Path(source_name).stem}.json"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(structured_output)
        except (FileNotFoundError, PermissionError, OSError) as e:
            self.stream_error_and_exit(f"Error creating output file: {e}")
        except json.JSONDecodeError as e:
            self.stream_error_and_exit(f"Error encoding JSON: {e}")
        self.write_tool_result(data=json.loads(structured_output))

    def _summarize_and_index(
        self,
        tool_id: str,
        tool_settings: dict[str, Any],
        tool_data_dir: Path,
        responder: PromptTool,
        outputs: dict[str, Any],
        index: Index,
        usage_kwargs: dict[Any, Any] = {},
        enable_highlight: bool = False,
    ) -> str:
        """Summarizes the context of the file and indexes the summarized
        content.

        Args:
            tool_id (str): The identifier of the tool.
            tool_settings (dict[str, Any]): Settings for the tool.
            tool_data_dir (Path): Directory where tool data is stored.
            responder (PromptTool): Instance of a tool used to generate the summary.
            outputs (dict[str, Any]): Dictionary containing prompt details.
            index (Index): Instance used to index the summarized content.

        Returns:
            str: The hash of the summarized file.
        """
        llm_adapter_instance_id: str = tool_settings[SettingsKeys.LLM]
        embedding_instance_id: str = tool_settings[SettingsKeys.EMBEDDING]
        vector_db_instance_id: str = tool_settings[SettingsKeys.VECTOR_DB]
        x2text_instance_id: str = tool_settings[SettingsKeys.X2TEXT_ADAPTER]
        summarize_prompt: str = tool_settings[SettingsKeys.SUMMARIZE_PROMPT]
        run_id: str = usage_kwargs.get(SettingsKeys.RUN_ID)
        extract_file_path = tool_data_dir / SettingsKeys.EXTRACT
        summarize_file_path = tool_data_dir / SettingsKeys.SUMMARIZE

        summarized_context = ""
        if summarize_file_path.exists():
            with open(summarize_file_path, encoding="utf-8") as f:
                summarized_context = f.read()
        if not summarized_context:
            context = ""
            with open(extract_file_path, encoding="utf-8") as file:
                context = file.read()
            prompt_keys = []
            for output in outputs:
                prompt_keys.append(output[SettingsKeys.NAME])
                output[SettingsKeys.EMBEDDING] = embedding_instance_id
                output[SettingsKeys.VECTOR_DB] = vector_db_instance_id
                output[SettingsKeys.X2TEXT_ADAPTER] = x2text_instance_id
                output[SettingsKeys.CHUNK_SIZE] = 0
                output[SettingsKeys.CHUNK_OVERLAP] = 0
            self.stream_log("Summarizing context")
            payload = {
                SettingsKeys.RUN_ID: run_id,
                SettingsKeys.LLM_ADAPTER_INSTANCE_ID: llm_adapter_instance_id,
                SettingsKeys.SUMMARIZE_PROMPT: summarize_prompt,
                SettingsKeys.CONTEXT: context,
                SettingsKeys.PROMPT_KEYS: prompt_keys,
            }
            response = responder.summarize(payload=payload)
            if response[SettingsKeys.STATUS] != SettingsKeys.OK:
                self.stream_error_and_exit(
                    f"Error summarizing response: {response[SettingsKeys.ERROR]}"
                )
            structure_output = json.loads(response[SettingsKeys.STRUCTURE_OUTPUT])
            summarized_context = structure_output.get(SettingsKeys.DATA, "")
            self.stream_log("Writing summarized context to a file")
            with open(summarize_file_path, "w", encoding="utf-8") as f:
                f.write(summarized_context)

        self.stream_log("Indexing summarized context")
        summarize_file_hash: str = ToolUtils.get_hash_from_file(
            file_path=summarize_file_path
        )
        index.index(
            tool_id=tool_id,
            embedding_instance_id=embedding_instance_id,
            vector_db_instance_id=vector_db_instance_id,
            x2text_instance_id=x2text_instance_id,
            file_path=summarize_file_path,
            file_hash=summarize_file_hash,
            chunk_size=0,
            chunk_overlap=0,
            usage_kwargs=usage_kwargs,
            enable_highlight=enable_highlight,
        )
        return summarize_file_hash


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = StructureTool.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
