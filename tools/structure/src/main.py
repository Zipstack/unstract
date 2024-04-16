import json
import sys
from pathlib import Path
from typing import Any

from constants import SettingsKeys  # type: ignore [attr-defined]
from unstract.sdk.constants import LogState, MetadataKey
from unstract.sdk.index import ToolIndex
from unstract.sdk.prompt import PromptTool
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint


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
        responder = PromptTool(
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

        self.stream_log("Indexing document...")
        file_hash = self.get_exec_metadata.get(MetadataKey.SOURCE_HASH)
        tool_index = ToolIndex(tool=self)
        tool_id = tool_metadata[SettingsKeys.TOOL_ID]
        outputs = tool_metadata[SettingsKeys.OUTPUTS]
        try:
            for output in outputs:
                tool_index.index_file(
                    tool_id=tool_metadata[SettingsKeys.TOOL_ID],
                    embedding_type=output[SettingsKeys.EMBEDDING],
                    vector_db=output[SettingsKeys.VECTOR_DB],
                    x2text_adapter=output[SettingsKeys.X2TEXT_ADAPTER],
                    file_path=input_file,
                    file_hash=file_hash,
                    chunk_size=output[SettingsKeys.CHUNK_SIZE],
                    chunk_overlap=output[SettingsKeys.CHUNK_OVERLAP],
                    reindex=output[SettingsKeys.REINDEX],
                )
        except Exception as e:
            self.stream_error_and_exit(f"Error fetching data and indexing: {e}")

        # TODO : Check if reindex. If Yes, reindex, else continue.
        payload = {
            "outputs": outputs,
            "tool_id": tool_id,
            "file_hash": file_hash,
        }
        self.stream_log("Fetching responses for prompts...")
        prompt_service_resp = responder.answer_prompt(payload=payload)

        # TODO: Make use of dataclasses
        if prompt_service_resp["status"] == "ERROR":
            self.stream_error_and_exit(
                f"Failed to fetch responses for "
                f"prompts: {prompt_service_resp['error']}"
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


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = StructureTool.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
