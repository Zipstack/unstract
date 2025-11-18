from qdrant_client.http.exceptions import ApiException as QdrantAPIException
from unstract.sdk1.adapters.vectordb.qdrant.src import Qdrant
from unstract.sdk1.adapters.vectordb.vectordb_adapter import VectorDBAdapter
from unstract.sdk1.exceptions import VectorDBError


def parse_vector_db_err(e: Exception, vector_db: VectorDBAdapter) -> VectorDBError:
    """Parses the exception from vector DB provider.

    Helps parse the vector DB error and wraps it with our
    custom exception object to contain a user friendly message.

    Args:
        e (Exception): Error from vector DB provider

    Returns:
        VectorDBError: Unstract's VectorDBError object
    """
    # Avoid wrapping VectorDBError objects again
    if isinstance(e, VectorDBError):
        return e

    if isinstance(e, QdrantAPIException):
        err = Qdrant.parse_vector_db_err(e)
    else:
        err = VectorDBError(str(e), actual_err=e)

    msg = f"Error from vector DB '{vector_db.get_name()}'."

    # Add a code block only for errors from clients
    if err.actual_err:
        msg += f"\n```\n{str(err)}\n```"
    else:
        msg += str(err)
    err.message = msg
    return err
