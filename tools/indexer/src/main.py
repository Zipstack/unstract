import sys
from typing import Any

from constants import SettingsKeys
from unstract.sdk.constants import LogState, MetadataKey, ToolSettingsKey
from unstract.sdk.index import ToolIndex
from unstract.sdk.tool.base import BaseTool
from unstract.sdk.tool.entrypoint import ToolEntrypoint


class DocumentIndexer(BaseTool):
    def run(
        self,
        settings: dict[str, Any],
        input_file: str,
        output_dir: str,
    ) -> None:
        # Update GUI
        input_log = (
            "### Indexing file\n"
            "```text\n"
            f"- Chunk Size: {settings[SettingsKeys.CHUNK_SIZE]}\n"
            f"- Chunk Overlap: {settings[SettingsKeys.CHUNK_OVERLAP]}\n"
            f"- Re-index: {settings[SettingsKeys.REINDEX]}\n"
            "```\n\n"
        )
        output_log = ""
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        file_hash = self.get_exec_metadata.get(MetadataKey.SOURCE_HASH)
        if not file_hash:
            raise RuntimeError("Source hash missing in metadata")
        tool_index = ToolIndex(tool=self)
        self.stream_log("Indexing document...")
        try:
            tool_index.index_file(
                tool_id=self.workflow_id,
                embedding_type=settings[ToolSettingsKey.EMBEDDING_ADAPTER_ID],
                vector_db=settings[ToolSettingsKey.VECTOR_DB_ADAPTER_ID],
                x2text_adapter=settings[ToolSettingsKey.X2TEXT_ADAPTER_ID],
                file_path=input_file,
                file_hash=file_hash,
                chunk_size=settings[SettingsKeys.CHUNK_SIZE],
                chunk_overlap=settings[SettingsKeys.CHUNK_OVERLAP],
                reindex=settings[SettingsKeys.REINDEX],
            )
        except Exception as e:
            self.stream_error_and_exit(f"Error fetching data and indexing: {e}")
        index_key = ToolIndex.generate_file_id(
            tool_id=self.workflow_id,
            file_hash=file_hash,
            vector_db=settings[ToolSettingsKey.VECTOR_DB_ADAPTER_ID],
            embedding=settings[ToolSettingsKey.EMBEDDING_ADAPTER_ID],
            x2text=settings[ToolSettingsKey.X2TEXT_ADAPTER_ID],
            chunk_size=settings[SettingsKeys.CHUNK_SIZE],
            chunk_overlap=settings[SettingsKeys.CHUNK_OVERLAP],
        )
        # Update GUI
        input_log = (
            "### Indexing file\n"
            "```text\n"
            f"- Chunk Size: {settings[SettingsKeys.CHUNK_SIZE]}\n"
            f"- Chunk Overlap: {settings[SettingsKeys.CHUNK_OVERLAP]}\n"
            f"- Re-index: {settings[SettingsKeys.REINDEX]}\n"
            "```\n\n"
        )
        output_log = f"### Index results\n File indexed against key {index_key}"
        self.stream_update(input_log, state=LogState.INPUT_UPDATE)
        self.stream_update(output_log, state=LogState.OUTPUT_UPDATE)

        self.write_tool_result(data=f"File indexed successfully at {index_key}")


if __name__ == "__main__":
    args = sys.argv[1:]
    tool = DocumentIndexer.from_tool_args(args=args)
    ToolEntrypoint.launch(tool=tool, args=args)
