"""is_vector_store_not_found: only a missing index may be treated as "not indexed".

A Qdrant collection is created on the first write, so the first existence check
legitimately answers 404. Any other failure means the check could not be
answered; treating that as "not indexed yet" indexes a second copy of the
document and the run still reports success.
"""

from unstract.sdk1.exceptions import is_vector_store_not_found


class _HttpError(Exception):
    def __init__(self, status_code=None, response=None):
        super().__init__(f"HTTP {status_code}")
        if status_code is not None:
            self.status_code = status_code
        if response is not None:
            self.response = response


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def test_status_code_404_is_not_found():
    assert is_vector_store_not_found(_HttpError(status_code=404))


def test_response_status_code_404_is_not_found():
    assert is_vector_store_not_found(_HttpError(response=_Response(404)))


def test_other_status_code_is_not_treated_as_missing_index():
    assert not is_vector_store_not_found(_HttpError(status_code=500))


def test_timeout_is_not_treated_as_missing_index():
    assert not is_vector_store_not_found(TimeoutError("read timed out"))


def test_wrapped_404_is_not_found():
    try:
        try:
            raise _HttpError(status_code=404)
        except _HttpError as cause:
            raise RuntimeError("vector store query failed") from cause
    except RuntimeError as error:
        assert is_vector_store_not_found(error)


def test_plain_error_is_not_missing_index():
    assert not is_vector_store_not_found(ValueError("bad query"))


def test_cyclic_cause_chain_terminates():
    first = RuntimeError("first")
    second = RuntimeError("second")
    first.__cause__ = second
    second.__cause__ = first

    assert not is_vector_store_not_found(first)
