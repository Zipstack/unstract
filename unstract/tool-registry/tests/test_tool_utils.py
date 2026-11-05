import pytest

from unstract.tool_registry.tool_utils import ToolUtils


@pytest.mark.parametrize(
    "image_url",
    [
        "local:classifier",
        "local:text-extractor",
        "local:classifier:0.0.1",
        "local:/opt/tools/classifier",
    ],
)
def test_valid_local_tool_url(image_url: str) -> None:
    assert ToolUtils.is_valid_tool_url(image_url)


@pytest.mark.parametrize(
    "image_url",
    ["local:", "local:bad name", "local:tool;rm", "local:tool@sha"],
)
def test_invalid_local_tool_url(image_url: str) -> None:
    assert not ToolUtils.is_valid_tool_url(image_url)
