from dataclasses import dataclass, field
from typing import Any


@dataclass
class InstanceIdentifiers:
    embedding_instance_id: str
    vector_db_instance_id: str
    x2text_instance_id: str
    llm_instance_id: str
    tool_id: str
    tags: list[str] | None = None


@dataclass
class FileInfo:
    file_path: str
    file_hash: str


@dataclass
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int

    def __post_init__(self) -> None:
        if self.chunk_size == 0:
            raise ValueError(
                "Indexing cannot be done for zero chunks."
                "Please provide a valid chunk_size."
            )


@dataclass
class ProcessingOptions:
    reindex: bool = False
    enable_highlight: bool = False
    usage_kwargs: dict[Any, Any] = field(default_factory=dict)
