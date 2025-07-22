import json

from unstract.sdk1.file_storage import FileStorage, FileStorageProvider
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils import ToolUtils


class IndexingUtils:
    @staticmethod
    def generate_index_key(
        vector_db: str,
        embedding: str,
        x2text: str,
        chunk_size: str,
        chunk_overlap: str,
        tool: BaseTool,
        file_path: str | None = None,
        file_hash: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        """Generates a unique index key based on the provided configuration,
        file information, instance identifiers, and processing options.

        Args:
            fs (FileStorage, optional): File storage for remote storage.

        Returns:
            str: A unique index key used for indexing the document.
        """
        if not file_path and not file_hash:
            raise ValueError("One of `file_path` or `file_hash` need to be provided")

        if not file_hash:
            file_hash = fs.get_hash_from_file(path=file_path)

        # Whole adapter config is used currently even though it contains some keys
        # which might not be relevant to indexing. This is easier for now than
        # marking certain keys of the adapter config as necessary.
        index_key = {
            "file_hash": file_hash,
            "vector_db_config": PlatformHelper.get_adapter_config(tool, vector_db),
            "embedding_config": PlatformHelper.get_adapter_config(tool, embedding),
            "x2text_config": PlatformHelper.get_adapter_config(tool, x2text),
            # Typed and hashed as strings since the final hash is persisted
            # and this is required to be backward compatible
            "chunk_size": str(chunk_size),
            "chunk_overlap": str(chunk_overlap),
        }
        # JSON keys are sorted to ensure that the same key gets hashed even in
        # case where the fields are reordered.
        hashed_index_key = ToolUtils.hash_str(json.dumps(index_key, sort_keys=True))
        return hashed_index_key
