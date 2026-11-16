import pytest
from pydantic import ValidationError
from unstract.sdk1.adapters.base1 import (
    OpenAIEmbeddingParameters,
    OpenAILLMParameters,
)

_KEY = "STANDINKEYabcdefghijklmnop"


@pytest.mark.parametrize("parameters", [OpenAILLMParameters, OpenAIEmbeddingParameters])
def test_validation_error_names_the_field_but_not_the_settings(parameters: type) -> None:
    with pytest.raises(ValidationError) as caught:
        parameters(api_key=_KEY)

    assert "model" in str(caught.value)
    assert _KEY[:8] not in str(caught.value)
