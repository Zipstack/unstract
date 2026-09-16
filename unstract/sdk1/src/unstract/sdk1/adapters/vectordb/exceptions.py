from unstract.sdk1.adapters.vectordb.vectordb_adapter import VectorDBAdapter
from unstract.sdk1.exceptions import VectorDBError


def parse_vector_db_err(e: Exception, vector_db: VectorDBAdapter) -> VectorDBError:
    """Parses the exception from LLM provider.

    Helps parse the LLM error and wraps it with our
    custom exception object to contain a user friendly message.

    Args:
        e (Exception): Error from LLM provider

    Returns:
        LLMError: Unstract's LLMError object
    """
    # Avoid wrapping VectorDBError objects again
    if isinstance(e, VectorDBError):
        return e

    # Lazy import to avoid hard dependency on qdrant_client at module level.
    # qdrant_client's protobuf files can fail to load depending on the
    # protobuf runtime version (KeyError: '_POINTID').
    try:
        from qdrant_client.http.exceptions import ApiException as QdrantAPIException

        from unstract.sdk1.adapters.vectordb.qdrant.src import Qdrant

        if isinstance(e, QdrantAPIException):
            err = Qdrant.parse_vector_db_err(e)
        else:
            err = VectorDBError(str(e), actual_err=e)
    except Exception:
        err = VectorDBError(str(e), actual_err=e)

    msg = f"Error from vector DB '{vector_db.get_name()}'."

    # Add a code block only for errors from clients
    if err.actual_err:
        msg += f"\n```\n{str(err)}\n```"
    else:
        msg += str(err)
    err.message = msg
    return err
