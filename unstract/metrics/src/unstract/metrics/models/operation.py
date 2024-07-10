from elasticsearch_dsl import Date, InnerDoc, Integer, Keyword, Nested, Object, Text

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
