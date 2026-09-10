"""The postprocessing webhook guard must live in the sink, not in its caller.

The URL check used to run one frame up in ``answer_prompt``, which left any
new caller of ``_make_webhook_request`` to remember it. It now sits in the
sink; these tests call the sink directly.

Both directions are covered on purpose. Refusing every blocked URL is easy to
get right and easy to over-do: a guard that refuses *everything* silently
disables postprocessing for every tenant, and — because a refusal returns the
unprocessed data on a run still reported successful — nothing else in the
suite would notice. The allow-path cases are what pin that.

The notification sink's equivalent tests live in
``unstract/core/tests/test_ssrf_guard.py``, next to that sink.
"""

from unittest.mock import patch

import pytest
from executor.executors.answer_prompt import AnswerPromptService
from executor.executors.postprocessor import _make_webhook_request

BLOCKED_URLS = [
    "https://169.254.169.254/latest/meta-data/",  # cloud metadata
    "https://127.0.0.1:8000/admin/",
    r"https://127.0.0.1:6666\@1.1.1.1",  # parsers disagree on the host
    "http://example.com/hook",  # this path has always required TLS
]

# Stub DNS so the allow-path cases do not depend on the network.
_FAKE_DNS = {"hook.example.com": "93.184.216.34"}


@pytest.fixture
def stub_dns(monkeypatch):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host not in _FAKE_DNS:
            raise OSError(f"unresolvable in test: {host}")
        return [(None, None, None, "", (_FAKE_DNS[host], 0))]

    monkeypatch.setattr(
        "unstract.core.network.ssrf.socket.getaddrinfo", fake_getaddrinfo
    )


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_postprocessor_sink_refuses_without_calling_out(url):
    with patch("executor.executors.postprocessor.requests.post") as post:
        assert _make_webhook_request(url, {"payload": 1}, timeout=5) is None
    post.assert_not_called()


def test_postprocessor_sink_still_calls_a_public_https_url(stub_dns):
    """Without this, a guard that refuses everything keeps the suite green."""
    with patch("executor.executors.postprocessor.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {"structured_output": {"field": "new"}}
        result = _make_webhook_request(
            "https://hook.example.com/hook", {"payload": 1}, timeout=5
        )

    post.assert_called_once()
    assert post.call_args.kwargs["allow_redirects"] is False
    assert result == {"structured_output": {"field": "new"}}


class TestRunWebhookPostprocess:
    """``_run_webhook_postprocess`` is the caller that used to hold the guard.

    It no longer checks the URL itself — the sink does — so what matters here
    is that it still reaches the sink, and that a refusal leaves the caller's
    data untouched rather than raising into the executor.
    """

    PARSED = {"field": "original"}

    def test_missing_url_skips_without_touching_the_network(self):
        with patch("executor.executors.postprocessor.requests.post") as post:
            result, highlights = AnswerPromptService._run_webhook_postprocess(
                parsed_data=self.PARSED, webhook_url=None, highlight_data=None
            )
        post.assert_not_called()
        assert result == self.PARSED
        assert highlights is None

    def test_refused_url_returns_the_original_data(self, stub_dns):
        with patch("executor.executors.postprocessor.requests.post") as post:
            result, _ = AnswerPromptService._run_webhook_postprocess(
                parsed_data=self.PARSED,
                webhook_url="https://127.0.0.1/hook",
                highlight_data=None,
            )
        post.assert_not_called()
        assert result == self.PARSED

    def test_allowed_url_is_delivered_and_its_output_used(self, stub_dns):
        """The guard is applied once, in the sink, and does not block a real URL."""
        with patch("executor.executors.postprocessor.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                "structured_output": {"field": "processed"}
            }
            result, _ = AnswerPromptService._run_webhook_postprocess(
                parsed_data=self.PARSED,
                webhook_url="https://hook.example.com/hook",
                highlight_data=None,
            )

        post.assert_called_once()
        assert result == {"field": "processed"}

    def test_the_guard_runs_only_once_per_call(self, monkeypatch):
        """The caller-side check was removed; resolving twice was its only cost."""
        lookups = []

        def counting_getaddrinfo(host, *_args, **_kwargs):
            lookups.append(host)
            return [(None, None, None, "", (_FAKE_DNS[host], 0))]

        monkeypatch.setattr(
            "unstract.core.network.ssrf.socket.getaddrinfo", counting_getaddrinfo
        )
        with patch("executor.executors.postprocessor.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"structured_output": {}}
            AnswerPromptService._run_webhook_postprocess(
                parsed_data=self.PARSED,
                webhook_url="https://hook.example.com/hook",
                highlight_data=None,
            )

        assert lookups == ["hook.example.com"]
