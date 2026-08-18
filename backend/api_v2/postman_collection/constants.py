class CollectionKey:
    POSTMAN_COLLECTION_V210 = (
        "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"  # noqa: E501
    )
    EXECUTE_API_KEY = "Process document"
    EXECUTE_PIPELINE_API_KEY = "Process pipeline"
    STATUS_API_KEY = "Execution status"
    STATUS_EXEC_ID_DEFAULT = "REPLACE_WITH_EXECUTION_ID"
    EXEC_ID_VARIABLE_NAME = "execution_id"
    # Derive the Postman variable reference from the variable name so the two
    # can never drift apart (-> "{{execution_id}}").
    STATUS_EXEC_ID_VARIABLE = f"{{{{{EXEC_ID_VARIABLE_NAME}}}}}"
    AUTH_QUERY_PARAM_DEFAULT = "REPLACE_WITH_API_KEY"
