from elasticsearch_dsl import (
    Date,
    Document,
    Float,
    InnerDoc,
    Integer,
    Keyword,
    Nested,
    Object,
    Text,
)

from .operation import Operation


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


class Metrics(Document):
    org_id = Keyword(required=True)
    run_id = Keyword(required=True)
    start_time = Date(required=True)
    end_time = Date(required=True)
    owner = Keyword()
    agent = Keyword()  # TODO: Enum - WF | API | PS
    agent_name = Text()
    agent_id = Keyword()
    status = Keyword()  # TODO: Make enum
    api_key = Text()
    operations = Nested(Operation)

    class Index:
        name = "unstract-metrics-*"
        settings = {"number_of_replicas": 0, "number_of_shards": 1}

    def save(
        self,
        using=None,
        index=None,
        validate=True,
        skip_empty=True,
        return_doc_meta=False,
        **kwargs,
    ):
        self.meta.id = self.run_id
        return super().save(
            using, index, validate, skip_empty, return_doc_meta, **kwargs
        )

    @classmethod
    def create_index(cls):
        cls.init()
        # Add dynamic templates for sub_process specific mappings
        cls._index.put_mapping(
            body={
                "dynamic_templates": [
                    {
                        "llm_template": {
                            "path_match": "operations.sub_process",
                            "match_mapping_type": "string",
                            "mapping": {
                                "type": "nested",
                                "properties": LLMOperation._doc_type.mapping.properties.to_dict(),  # noqa: E501
                            },
                            "match": "LLM",
                        }
                    },
                    {
                        "vectordb_template": {
                            "path_match": "operations.sub_process",
                            "match_mapping_type": "string",
                            "mapping": {
                                "type": "nested",
                                "properties": VectorDBOperation._doc_type.mapping.properties.to_dict(),  # noqa: E501
                            },
                            "match": "VECTORDB",
                        }
                    },
                    {
                        "embedding_template": {
                            "path_match": "operations.sub_process",
                            "match_mapping_type": "string",
                            "mapping": {
                                "type": "nested",
                                "properties": EmbeddingOperation._doc_type.mapping.properties.to_dict(),  # noqa: E501
                            },
                            "match": "EMBEDDING",
                        }
                    },
                ]
            }
        )
