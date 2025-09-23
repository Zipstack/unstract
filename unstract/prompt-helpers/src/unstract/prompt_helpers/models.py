"""Common data models for prompt helpers.

This module contains Pydantic models used across the prompt helpers
to ensure type safety and data validation.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator


class ProcessingStatus(str, Enum):
    """Processing status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChunkingStrategy(str, Enum):
    """Chunking strategy enumeration."""
    FIXED_SIZE = "fixed_size"
    SENTENCE_BASED = "sentence_based"
    SEMANTIC = "semantic"
    SMART = "smart"  # Context-aware chunking
    PARAGRAPH = "paragraph"
    DOCUMENT_STRUCTURE = "document_structure"


class RAGStrategy(str, Enum):
    """RAG retrieval strategy enumeration."""
    SIMPLE = "simple"
    SUBQUESTION = "subquestion"
    FUSION = "fusion"
    RECURSIVE = "recursive"
    ROUTER = "router"
    KEYWORD_TABLE = "keyword_table"
    AUTOMERGING = "automerging"


class EvaluationType(str, Enum):
    """Evaluation type enumeration."""
    QUALITY_FAITHFULNESS = "quality_faithfulness"
    QUALITY_CORRECTNESS = "quality_correctness"
    QUALITY_RELEVANCE = "quality_relevance"
    SECURITY_PII = "security_pii"
    GUIDANCE_TOXICITY = "guidance_toxicity"
    GUIDANCE_COMPLETENESS = "guidance_completeness"


class OutputType(str, Enum):
    """Output type enumeration."""
    TEXT = "text"
    NUMBER = "number"
    EMAIL = "email"
    DATE = "date"
    BOOLEAN = "boolean"
    JSON = "json"
    TABLE = "table"
    LINE_ITEM = "line_item"


# Base models
class BaseResult(BaseModel):
    """Base result model with common fields."""
    
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: ProcessingStatus = ProcessingStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def mark_completed(self, processing_time_ms: Optional[int] = None) -> None:
        """Mark result as completed."""
        self.status = ProcessingStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if processing_time_ms is not None:
            self.processing_time_ms = processing_time_ms
    
    def mark_failed(self, error_message: str) -> None:
        """Mark result as failed."""
        self.status = ProcessingStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message


class ProcessingResult(BaseResult):
    """Generic processing result."""
    
    result: Any = None
    result_type: Optional[str] = None


class ExtractionResult(BaseResult):
    """Text extraction result."""
    
    extracted_text: Optional[str] = None
    file_path: Optional[str] = None
    extraction_method: Optional[str] = None
    page_count: Optional[int] = None
    character_count: Optional[int] = None
    word_count: Optional[int] = None
    confidence_score: Optional[float] = None


class ChunkingResult(BaseResult):
    """Chunking result."""
    
    chunks: List[str] = Field(default_factory=list)
    chunk_count: int = 0
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.FIXED_SIZE
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    total_characters: Optional[int] = None
    
    @validator("chunk_count", always=True)
    def set_chunk_count(cls, v, values):
        """Automatically set chunk count based on chunks."""
        chunks = values.get("chunks", [])
        return len(chunks)


class EmbeddingResult(BaseResult):
    """Embedding generation result."""
    
    embeddings: List[List[float]] = Field(default_factory=list)
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    chunk_count: Optional[int] = None
    doc_id: Optional[str] = None
    vector_db_stored: bool = False


class EvaluationResult(BaseResult):
    """Evaluation result."""
    
    evaluation_type: EvaluationType
    score: Optional[float] = None
    passed: Optional[bool] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    evaluation_model: Optional[str] = None
    threshold: Optional[float] = None


class LLMProcessingResult(BaseResult):
    """LLM processing result."""
    
    response: Optional[str] = None
    prompt: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class RAGResult(BaseResult):
    """RAG processing result."""
    
    response: Optional[str] = None
    retrieved_chunks: List[str] = Field(default_factory=list)
    retrieval_strategy: RAGStrategy = RAGStrategy.SIMPLE
    similarity_scores: List[float] = Field(default_factory=list)
    top_k: Optional[int] = None
    doc_id: Optional[str] = None
    query: Optional[str] = None


# Configuration models
class TextExtractionConfig(BaseModel):
    """Configuration for text extraction."""
    
    x2text_instance_id: Optional[str] = None
    enable_ocr: bool = True
    ocr_confidence_threshold: float = 0.7
    preserve_formatting: bool = True
    extract_tables: bool = True
    extract_images: bool = False
    languages: List[str] = Field(default_factory=lambda: ["en"])
    timeout_seconds: int = 300


class ChunkingConfig(BaseModel):
    """Configuration for text chunking."""
    
    strategy: ChunkingStrategy = ChunkingStrategy.SMART
    chunk_size: int = 1000
    chunk_overlap: int = 100
    min_chunk_size: int = 50
    max_chunk_size: Optional[int] = None
    separator: str = "\n\n"
    preserve_sentence_boundaries: bool = True
    remove_empty_chunks: bool = True


class EmbeddingConfig(BaseModel):
    """Configuration for embedding generation."""
    
    embedding_adapter_id: str
    batch_size: int = 32
    normalize_embeddings: bool = True
    store_in_vector_db: bool = True
    vector_db_adapter_id: Optional[str] = None
    collection_name: Optional[str] = None


class LLMConfig(BaseModel):
    """Configuration for LLM processing."""
    
    adapter_instance_id: str
    temperature: float = 0.1
    max_tokens: int = 4000
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop_sequences: List[str] = Field(default_factory=list)
    timeout_seconds: int = 120


class RAGConfig(BaseModel):
    """Configuration for RAG processing."""
    
    llm_adapter_id: str
    embedding_adapter_id: str
    vector_db_adapter_id: str
    strategy: RAGStrategy = RAGStrategy.SIMPLE
    similarity_top_k: int = 5
    similarity_threshold: float = 0.7
    max_context_length: int = 4000
    chunk_size: int = 1000
    chunk_overlap: int = 100
    enable_reranking: bool = False
    rerank_top_k: Optional[int] = None


class EvaluationConfig(BaseModel):
    """Configuration for evaluation."""
    
    evaluation_types: List[EvaluationType]
    monitor_llm_adapter_id: Optional[str] = None
    
    # Quality thresholds
    faithfulness_threshold: float = 0.7
    correctness_threshold: float = 0.8
    relevance_threshold: float = 0.7
    
    # Security settings
    pii_detection_enabled: bool = True
    pii_entities: List[str] = Field(default_factory=lambda: ["PERSON", "EMAIL", "PHONE", "SSN"])
    
    # Guidance settings
    toxicity_threshold: float = 0.5
    completeness_threshold: float = 0.8


class FormattingConfig(BaseModel):
    """Configuration for output formatting."""
    
    output_type: OutputType = OutputType.TEXT
    enforce_type: bool = True
    format_template: Optional[str] = None
    validation_rules: List[str] = Field(default_factory=list)
    post_processing_steps: List[str] = Field(default_factory=list)
    
    # Table-specific settings
    table_extraction_enabled: bool = False
    table_format: str = "markdown"  # markdown, html, csv
    preserve_table_structure: bool = True
    
    # JSON-specific settings
    json_schema: Optional[Dict[str, Any]] = None
    validate_json: bool = True


# Workflow integration models
class WorkflowContext(BaseModel):
    """Context for workflow execution."""
    
    workflow_id: str
    task_name: str
    run_id: Optional[str] = None
    execution_id: Optional[str] = None
    user_context: Dict[str, Any] = Field(default_factory=dict)
    task_outputs: Dict[str, Any] = Field(default_factory=dict)
    
    def add_task_output(self, task_name: str, output: Any) -> None:
        """Add output from a completed task."""
        self.task_outputs[task_name] = output
    
    def get_task_output(self, task_name: str, default: Any = None) -> Any:
        """Get output from a previously completed task."""
        return self.task_outputs.get(task_name, default)


class HelperRegistry(BaseModel):
    """Registry for helper instances and configurations."""
    
    llm_helpers: Dict[str, LLMConfig] = Field(default_factory=dict)
    extraction_configs: Dict[str, TextExtractionConfig] = Field(default_factory=dict)
    chunking_configs: Dict[str, ChunkingConfig] = Field(default_factory=dict)
    embedding_configs: Dict[str, EmbeddingConfig] = Field(default_factory=dict)
    rag_configs: Dict[str, RAGConfig] = Field(default_factory=dict)
    evaluation_configs: Dict[str, EvaluationConfig] = Field(default_factory=dict)
    
    def register_llm_helper(self, name: str, config: LLMConfig) -> None:
        """Register an LLM helper configuration."""
        self.llm_helpers[name] = config
    
    def get_llm_config(self, name: str) -> Optional[LLMConfig]:
        """Get LLM configuration by name."""
        return self.llm_helpers.get(name)