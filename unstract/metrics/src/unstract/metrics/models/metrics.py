import logging

from elasticsearch_dsl import Date, Document, Keyword, Nested, Text

from .operation import (
    EmbeddingOperation,
    LLMOperation,
    Operation,
    VectorDBOperation,
    X2TextOperation,
)

logger = logging.getLogger(__name__)


class Metrics(Document):
    org_id = Keyword(required=True)
    run_id = Keyword()
    start_time = Date(required=True)
    end_time = Date()
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
                    {
                        "embedding_template": {
                            "path_match": "operations.sub_process",
                            "match_mapping_type": "string",
                            "mapping": {
                                "type": "nested",
                                "properties": X2TextOperation._doc_type.mapping.properties.to_dict(),  # noqa: E501
                            },
                            "match": "X2TEXT",
                        }
                    },
                ]
            }
        )
