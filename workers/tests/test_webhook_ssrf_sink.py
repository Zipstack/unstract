"""The postprocessing webhook guard must live in the sink, not in its caller.

The URL check used to run one frame up in ``answer_prompt``, which left any
new caller of ``_make_webhook_request`` to remember it. It now sits in the
sink; these tests call the sink directly.

The notification sink's equivalent tests live in
``unstract/core/tests/test_ssrf_guard.py``, next to that sink.
"""

from unittest.mock import patch

import pytest
from executor.executors.postprocessor import _make_webhook_request

BLOCKED_URLS = [
    "https://169.254.169.254/latest/meta-data/",  # cloud metadata
    "https://127.0.0.1:8000/admin/",
    r"https://127.0.0.1:6666\@1.1.1.1",  # parsers disagree on the host
    "http://example.com/hook",  # this path has always required TLS
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_postprocessor_sink_refuses_without_calling_out(url):
    with patch("executor.executors.postprocessor.requests.post") as post:
        assert _make_webhook_request(url, {"payload": 1}, timeout=5) is None
    post.assert_not_called()
