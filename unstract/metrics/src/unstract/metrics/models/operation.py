from elasticsearch_dsl import (
    Date,
    Float,
    InnerDoc,
    Integer,
    Keyword,
    Nested,
    Object,
    Text,
)

from unstract.metrics.models.log import Log


class Operation(InnerDoc):
    operation_id = Keyword()
    process = Keyword()  # TODO: Specify enum
    sub_process = Keyword()  # LLM | VECTORDB | EMBEDDING | X2TEXT
    context = Text()  # REVIEW: Make Keyword() if we wish to search by filename
    status = Keyword()
    start_time = Date()
    end_time = Date()
    chunk_size = Integer(doc_values=False)
    chunk_overlap = Integer(doc_values=False)
    prompt_key_name = Text()
    # adapter_metadata = Object()
    connector_metadata = Object()
    metrics = Object()
    logs = Nested(Log)


class LLMOperation(InnerDoc):
    prompt = Text()
    generated_response = Text()
    adapter_metadata = Object(
        properties={
            "adapter_instance_id": Keyword(),
            "type": Keyword(),
            "name": Text(),
            "model": Text(),
            "max_retries": Integer(doc_values=False),
            "max_output_tokens": Integer(doc_values=False),
        }
    )
    metrics = Object(
        properties={
            "input_tokens": Integer(),
            "output_tokens": Integer(),
            "latency": Float(),
            "input_tokens_cost": Float(),
            "output_tokens_cost": Float(),
            "total_cost": Float(),
        }
    )


class VectorDBOperation(InnerDoc):
    doc_id = Keyword()
    retrieved_docs = Keyword(multi=True)
    adapter_metadata = Object(
        properties={
            "adapter_instance_id": Keyword(),
            "type": Keyword(),
            "name": Text(),
            "dimension": Integer(doc_values=False),
        }
    )
    metrics = Object(
        properties={"operation": Keyword(), "count": Integer(), "latency": Float()}
    )


class EmbeddingOperation(InnerDoc):
    adapter_metadata = Object(
        properties={
            "adapter_instance_id": Keyword(),
            "type": Keyword(),
            "name": Text(),
            "model": Text(),
            "embed_batch_size": Integer(),
        }
    )
    metrics = Object(
        properties={"tokens": Integer(), "latency": Float(), "cost": Float()}
    )


class X2TextOperation(InnerDoc):
    adapter_metadata = Object(
        properties={
            "adapter_instance_id": Keyword(),
            "type": Keyword(),
            "name": Text(),
            "mode": Text(),
        }
    )
    metrics = Object(
        properties={
            "pages_extracted": Integer(),
            "latency": Float(),
        }
    )
