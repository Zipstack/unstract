"""Tests for refreshing the image-limits table from GitHub.

Installs read ``limits.json`` from the repository's main branch so a data
fix reaches them without a release. The bundled copy is the fallback that
is always there: a slow, failing or bad remote file must never break image
mode. No test touches the network; HTTP goes through ``httpx.MockTransport``.

A refresh normally runs on a background thread; most tests run it inline
(``_start_background`` swapped for a direct call) so they can assert on its
result, and ``TestRequestPathNeverWaits`` exercises the real thread.
"""

import copy
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.utils import image_limits
from unstract.sdk1.utils.image_limits import (
    LIMITS_OVERRIDE_FILE_ENV,
    format_limit_source,
    get_limits_table,
    resolve_image_limits,
)
from unstract.sdk1.utils.image_limits import source as limits_source

BUNDLED = Path(image_limits.__file__).parent / "limits.json"
_REAL_HTTP_CLIENT = limits_source._http_client
URL = "https://limits.example/limits.json"


def _bundled_data() -> dict:
    return json.loads(BUNDLED.read_text())


def _remote_data(azure_images: int = 7, verified_on: str = "2026-11-01") -> dict:
    """The bundled table with a recognisable change, as main might publish it."""
    data = copy.deepcopy(_bundled_data())
    data["_meta"]["verified_on"] = verified_on
    data["providers"]["azure"]["defaults"]["max_images_per_request"]["value"] = (
        azure_images
    )
    return data


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _Server:
    """Counts requests and answers each with the configured handler."""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.handler = handler
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return self.handler(request)


def _json_response(data: object) -> Callable[[httpx.Request], httpx.Response]:
    body = json.dumps(data).encode()
    return lambda request: httpx.Response(200, content=body)


@pytest.fixture
def clock(monkeypatch: MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(limits_source, "_clock", fake)
    return fake


@pytest.fixture
def serve(monkeypatch: MonkeyPatch) -> Callable[..., _Server]:
    """Point the fetcher at a mock transport and enable the remote URL."""

    def _serve(handler: Callable[[httpx.Request], httpx.Response]) -> _Server:
        server = _Server(handler)
        monkeypatch.setenv(limits_source.LIMITS_URL_ENV, URL)
        monkeypatch.setattr(
            limits_source,
            "_http_client",
            lambda: httpx.Client(transport=httpx.MockTransport(server)),
        )
        return server

    return _serve


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch: MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(limits_source, "_start_background", lambda target: target())
    monkeypatch.delenv(LIMITS_OVERRIDE_FILE_ENV, raising=False)
    monkeypatch.delenv(limits_source.LIMITS_REFRESH_ENV, raising=False)
    image_limits.clear_limits_cache()
    yield
    image_limits.clear_limits_cache()


def _azure_images() -> int | None:
    return resolve_image_limits(
        "azure", "azure/my-dep", table=get_limits_table()
    ).max_images_per_request.value


class TestConfiguration:
    def test_default_url_is_limits_json_on_main(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv(limits_source.LIMITS_URL_ENV, raising=False)
        assert limits_source.configured_limits_url() == (
            "https://raw.githubusercontent.com/Zipstack/unstract/main/unstract/"
            "sdk1/src/unstract/sdk1/utils/image_limits/limits.json"
        )

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_url_disables_the_fetch(
        self, monkeypatch: MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(limits_source.LIMITS_URL_ENV, value)
        assert limits_source.configured_limits_url() is None

    def test_refresh_window_defaults_to_an_hour(self) -> None:
        assert limits_source.configured_refresh_seconds() == 3600

    def test_refresh_window_reads_the_env(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv(limits_source.LIMITS_REFRESH_ENV, "900")
        assert limits_source.configured_refresh_seconds() == 900

    @pytest.mark.parametrize("value", ["soon", "-5", "0"])
    def test_bad_refresh_window_falls_back_to_the_default(
        self, monkeypatch: MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv(limits_source.LIMITS_REFRESH_ENV, value)
        assert limits_source.configured_refresh_seconds() == 3600

    def test_refresh_window_has_a_floor(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv(limits_source.LIMITS_REFRESH_ENV, "1")
        assert limits_source.configured_refresh_seconds() == 60


class TestRemoteSuccess:
    def test_remote_table_is_used_and_recorded(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        serve(_json_response(_remote_data(azure_images=7)))

        assert _azure_images() == 7
        origin = get_limits_table().origin
        assert origin.source == "remote"
        assert origin.location == URL
        assert origin.verified_on == "2026-11-01"
        assert origin.schema_version == 1
        assert len(origin.sha256) == 12

    def test_source_and_version_reach_messages(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        serve(_json_response(_remote_data()))
        limits = resolve_image_limits("azure", "azure/my-dep", table=get_limits_table())

        assert "2026-11-01" in limits.table_version
        assert "remote" in limits.table_version
        text = format_limit_source(limits.max_images_per_request, limits)
        assert limits.table_version in text

    def test_success_is_logged_with_source_and_version(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        serve(_json_response(_remote_data()))
        with caplog.at_level("INFO"):
            get_limits_table()
        lines = [r.getMessage() for r in caplog.records]
        assert any(URL in line and "2026-11-01" in line for line in lines)

    def test_fetches_once_per_refresh_window(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data()))
        for _ in range(5):
            get_limits_table()
        clock.now += 3599
        get_limits_table()
        assert server.calls == 1

    def test_refreshes_after_the_window(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        assert _azure_images() == 7

        server.handler = _json_response(_remote_data(azure_images=9))
        clock.now += 3600
        assert _azure_images() == 9
        assert server.calls == 2

    def test_refresh_window_comes_from_the_env(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        monkeypatch: MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(limits_source.LIMITS_REFRESH_ENV, "120")
        server = serve(_json_response(_remote_data()))
        get_limits_table()
        clock.now += 120
        get_limits_table()
        assert server.calls == 2


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


_FAILURES = {
    "timeout": _raise(httpx.ReadTimeout("timed out")),
    "connect_error": _raise(httpx.ConnectError("no route to host")),
    "http_404": lambda request: httpx.Response(404, content=b"Not Found"),
    "http_500": lambda request: httpx.Response(500, content=b"boom"),
    "invalid_json": lambda request: httpx.Response(200, content=b"{not json"),
}


def _schema_invalid() -> dict:
    data = _remote_data()
    data["providers"]["azure"]["defaults"]["max_images_per_request"]["valu"] = 7
    return data


def _newer_schema() -> dict:
    data = _remote_data()
    data["_meta"]["schema_version"] = 2
    data["providers"]["azure"]["defaults"]["max_images_per_request"]["per_tier"] = {}
    return data


def _long_pattern() -> dict:
    data = _remote_data()
    data["providers"]["azure"]["model_overrides"][0]["pattern"] = "(?i)" + "a" * 400
    return data


def _invalid_regex() -> dict:
    data = _remote_data()
    data["providers"]["azure"]["model_overrides"][0]["pattern"] = "(?i)gpt-(4"
    return data


def _inherit_cycle() -> dict:
    # Greptile #2341: an override that inherits its own provider passed
    # loading and then recursed until RecursionError at lookup time.
    data = _bundled_data()
    data["providers"]["openai"].setdefault("model_overrides", []).insert(
        0, {"pattern": ".*", "description": "loop", "inherit": "openai"}
    )
    return data


_BAD_FILES = {
    "inherit_cycle": _inherit_cycle,
    "schema_invalid": _schema_invalid,
    "incompatible_schema_version": _newer_schema,
    "oversized_regex": _long_pattern,
    "invalid_regex": _invalid_regex,
}


class TestFallbackToBundled:
    @pytest.mark.parametrize("name", sorted(_FAILURES))
    def test_fetch_failure_serves_the_bundled_table(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
        name: str,
    ) -> None:
        serve(_FAILURES[name])

        assert _azure_images() == 50
        assert get_limits_table().origin.source == "bundled"
        assert any(r.levelname == "WARNING" for r in caplog.records)

    @pytest.mark.parametrize("name", sorted(_BAD_FILES))
    def test_bad_file_is_rejected_and_logged(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
        name: str,
    ) -> None:
        serve(_json_response(_BAD_FILES[name]()))

        assert _azure_images() == 50
        assert get_limits_table().origin.source == "bundled"
        assert any(
            r.levelname == "WARNING" and URL in r.getMessage() for r in caplog.records
        )

    def test_incompatible_schema_is_named_in_the_log(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        serve(_json_response(_newer_schema()))
        get_limits_table()
        assert any("schema_version" in r.getMessage() for r in caplog.records)

    def test_oversized_body_is_rejected(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        big = json.dumps(_remote_data()).encode() + b" " * 2_000_000
        serve(lambda request: httpx.Response(200, content=big))
        assert _azure_images() == 50

    def test_slow_body_is_abandoned_at_the_deadline(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        body = json.dumps(_remote_data()).encode()

        def trickle() -> Iterator[bytes]:
            for start in range(0, len(body), 1000):
                clock.now += 1  # each chunk takes a second
                yield body[start : start + 1000]

        serve(lambda request: httpx.Response(200, content=trickle()))
        assert _azure_images() == 50

    def test_failure_keeps_the_last_good_remote_table(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        assert _azure_images() == 7

        server.handler = _FAILURES["timeout"]
        clock.now += 3600
        assert _azure_images() == 7
        assert get_limits_table().origin.source == "remote"

    def test_bad_file_keeps_the_last_good_remote_table(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        assert _azure_images() == 7

        server.handler = _json_response(_newer_schema())
        clock.now += 3600
        assert _azure_images() == 7

    def test_failed_fetch_is_not_retried_inside_the_window(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_FAILURES["timeout"])
        for _ in range(5):
            get_limits_table()
        assert server.calls == 1

    def test_unexpected_error_never_escapes(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        serve(_raise(RuntimeError("transport bug")))
        assert _azure_images() == 50


def _drop_provider(key: str) -> Callable[[], dict]:
    def build() -> dict:
        data = _remote_data()
        del data["providers"][key]
        return data

    return build


class TestRemoteCannotDropAProvider:
    """A remote copy that loses a bundled provider is a bad file (O2).

    Otherwise the provider resolves as an advisory pass-through on every
    install within an hour: its documents are converted and billed, then
    rejected by the provider.
    """

    # Providers nothing inherits from (dropping an inherit target is already
    # a schema error), so only the drop check can reject these.
    @pytest.mark.parametrize("key", ["bedrock", "azure_ai", "minimax"])
    def test_table_dropping_a_provider_is_rejected(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
        key: str,
    ) -> None:
        serve(_json_response(_drop_provider(key)()))

        table = get_limits_table()
        assert table.origin.source == "bundled"
        assert key in table.providers
        assert any(
            r.levelname == "WARNING" and key in r.getMessage() and URL in r.getMessage()
            for r in caplog.records
        )

    def test_dropping_a_provider_keeps_the_last_good_remote_copy(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        assert _azure_images() == 7
        server.handler = _json_response(_drop_provider("bedrock")())
        clock.now += 3600
        assert _azure_images() == 7
        assert "bedrock" in get_limits_table().providers

    def test_resolution_falls_back_to_the_bundled_entry(self) -> None:
        # Even a table that slipped through (or one passed explicitly) never
        # turns a provider the bundled table knows into pass-through.
        from unstract.sdk1.utils.image_limits._schema import parse_limits_bytes

        table = parse_limits_bytes(
            json.dumps(_drop_provider("bedrock")()).encode(),
            source="remote",
            location=URL,
        )
        limits = resolve_image_limits(
            "bedrock", "bedrock/anthropic.claude-sonnet-4-5-v1:0", table=table
        )
        assert limits.provider_kind == "hosted"
        assert limits.is_default_provider is False
        assert limits.max_images_per_request.value == 20
        assert limits.max_images_per_request.advisory is False


def _mutated(mutate: Callable[[dict], None]) -> dict:
    data = _remote_data()
    mutate(data)
    return data


def _set(
    provider: str, field: str, value: int, override: int | None = None
) -> Callable[[dict], None]:
    def mutate(data: dict) -> None:
        entry = data["providers"][provider]
        target = (
            entry["defaults"] if override is None else entry["model_overrides"][override]
        )
        target[field]["value"] = value

    return mutate


def _set_kind(provider: str, kind: str) -> Callable[[dict], None]:
    return lambda data: data["providers"][provider].__setitem__("kind", kind)


def _shadow_bedrock_claude(data: dict) -> None:
    # A NEW override placed first that re-limits models the bundled table
    # already covers: entry-by-entry checks alone would miss it.
    override = copy.deepcopy(data["providers"]["bedrock"]["model_overrides"][-1])
    override["pattern"] = "(?i)claude-sonnet"
    override["max_images_per_request"]["value"] = 999
    data["providers"]["bedrock"]["model_overrides"].insert(0, override)


def _add_new_bedrock_model(data: dict) -> None:
    override = copy.deepcopy(data["providers"]["bedrock"]["model_overrides"][-1])
    override["pattern"] = "(?i)brand-new-vision-model"
    override["max_images_per_request"]["value"] = 999
    data["providers"]["bedrock"]["model_overrides"].insert(0, override)


def _add_provider(data: dict) -> None:
    data["providers"]["newco"] = copy.deepcopy(data["providers"]["openai"])


def _drop_bedrock_nova2(data: dict) -> None:
    # nova-2 is held to 5 images; without its override it would get 20.
    overrides = data["providers"]["bedrock"]["model_overrides"]
    assert overrides[0]["pattern"] == "(?i)nova-2"
    del overrides[0]


def _retarget_openrouter_anthropic(data: dict) -> None:
    overrides = data["providers"]["openrouter"]["model_overrides"]
    assert overrides[0]["inherit"] == "anthropic"
    overrides[0]["inherit"] = "gemini"


def _bedrock_images() -> int | None:
    return resolve_image_limits(
        "bedrock",
        "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0",
        table=get_limits_table(),
    ).max_images_per_request.value


class TestRemoteCannotLoosenEnforcement:
    """A remote copy may tighten freely but loosen only so far (O2).

    User decision (UN-4427): a provider's ``kind`` is locked, and an
    enforced image-count or request-byte limit may rise to at most 2x the
    bundled value. Otherwise one bad merge to main would loosen limits on
    every install within an hour, and documents would be converted and
    billed, then rejected by the provider.
    """

    _REJECTED = {
        "bedrock flipped to pass_through": _set_kind("bedrock", "pass_through"),
        "ollama flipped to hosted": _set_kind("ollama", "hosted"),
        "bedrock 20 images raised to 999": _set("bedrock", "max_images_per_request", 999),
        "bedrock 20 images raised to 41": _set("bedrock", "max_images_per_request", 41),
        "bedrock claude request bytes raised 2.5x": _set(
            "bedrock", "max_request_bytes", 50_000_000, override=2
        ),
        "table default raised (hosted fallback)": lambda data: data["default"][
            "max_images_per_request"
        ].__setitem__("value", 999),
        "new override shadows a known model": _shadow_bedrock_claude,
        "removed override loosens its models": _drop_bedrock_nova2,
        "inherit retargeted to a looser provider": _retarget_openrouter_anthropic,
    }
    _ACCEPTED = {
        "bedrock raised exactly 2x": _set("bedrock", "max_images_per_request", 40),
        "openai lowered to 1": _set("openai", "max_images_per_request", 1),
        "new provider": _add_provider,
        "new model override": _add_new_bedrock_model,
    }

    @pytest.mark.parametrize("name", sorted(_REJECTED))
    def test_loosening_table_is_rejected(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
        name: str,
    ) -> None:
        serve(_json_response(_mutated(self._REJECTED[name])))

        table = get_limits_table()
        assert table.origin.source == "bundled"
        assert any(
            r.levelname == "WARNING"
            and "Rejected image limits" in r.getMessage()
            and URL in r.getMessage()
            for r in caplog.records
        )

    @pytest.mark.parametrize("name", sorted(_ACCEPTED))
    def test_tightening_and_additions_are_accepted(
        self, serve: Callable[..., _Server], clock: _FakeClock, name: str
    ) -> None:
        serve(_json_response(_mutated(self._ACCEPTED[name])))
        assert get_limits_table().origin.source == "remote"

    def test_kind_flip_does_not_make_bedrock_advisory(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        serve(_json_response(_mutated(_set_kind("bedrock", "pass_through"))))
        limits = resolve_image_limits(
            "bedrock", "bedrock/meta.llama3-2-11b-instruct-v1:0", table=get_limits_table()
        )
        assert limits.provider_kind == "hosted"
        assert limits.max_request_bytes.advisory is False

    def test_rejection_keeps_the_last_good_remote_copy(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        assert _azure_images() == 7
        server.handler = _json_response(
            _mutated(_set("bedrock", "max_images_per_request", 999))
        )
        clock.now += 3600
        assert _azure_images() == 7
        assert _bedrock_images() == 20
        assert get_limits_table().origin.source == "remote"

    def test_reason_names_the_provider_and_the_numbers(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        serve(_json_response(_mutated(_set("bedrock", "max_images_per_request", 999))))
        get_limits_table()
        assert any(
            "bedrock defaults: max_images_per_request 20 -> 999" in r.getMessage()
            for r in caplog.records
        )

    def test_override_file_may_raise_limits(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        # The operator's own file is configuration, not a remote refresh:
        # the 2x rule does not apply to it.
        serve(_json_response(_remote_data(azure_images=7)))
        bedrock = copy.deepcopy(_bundled_data()["providers"]["bedrock"])
        for override in bedrock["model_overrides"]:
            override.pop("max_images_per_request", None)
        bedrock["defaults"]["max_images_per_request"]["value"] = 999
        path = tmp_path / "override.json"
        path.write_text(
            json.dumps(
                {"_meta": {"schema_version": 1}, "providers": {"bedrock": bedrock}}
            )
        )
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))
        assert _bedrock_images() == 999
        assert get_limits_table().origin.source == "remote"


class TestFetchIsBounded:
    def test_redirects_are_not_followed(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        monkeypatch: MonkeyPatch,
    ) -> None:
        body = json.dumps(_remote_data(azure_images=7)).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "elsewhere.example":
                return httpx.Response(200, content=body)
            return httpx.Response(
                302, headers={"location": "https://elsewhere.example/limits.json"}
            )

        server = serve(handler)
        # Use the real client factory (its redirect setting is under test),
        # with only the transport swapped for the mock.
        real_client = httpx.Client
        monkeypatch.setattr(limits_source, "_http_client", _REAL_HTTP_CLIENT)
        monkeypatch.setattr(
            limits_source.httpx,
            "Client",
            lambda **kw: real_client(transport=httpx.MockTransport(server), **kw),
        )
        assert _azure_images() == 50
        assert server.calls == 1

    def test_overall_deadline_covers_a_hung_request(
        self,
        serve: Callable[..., _Server],
        monkeypatch: MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # A hung DNS lookup or connect is outside httpx's per-phase timeouts;
        # the overall deadline still abandons it.
        monkeypatch.setattr(limits_source, "FETCH_TIMEOUT_SECONDS", 0.2)
        release = threading.Event()

        def hang(request: httpx.Request) -> httpx.Response:
            release.wait(5)
            return httpx.Response(200, content=json.dumps(_remote_data()).encode())

        serve(hang)
        started = time.monotonic()
        try:
            assert _azure_images() == 50
            elapsed = time.monotonic() - started
        finally:
            release.set()
        assert elapsed < 2
        assert any("within 0.2s" in r.getMessage() for r in caplog.records)


class TestRequestPathNeverWaits:
    """The refresh runs on a background thread behind a non-blocking lock."""

    def test_caller_is_served_while_the_refresh_runs(
        self, serve: Callable[..., _Server], monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            limits_source,
            "_start_background",
            lambda target: threading.Thread(target=target, daemon=True).start(),
        )
        entered, release = threading.Event(), threading.Event()
        body = json.dumps(_remote_data(azure_images=7)).encode()

        def slow(request: httpx.Request) -> httpx.Response:
            entered.set()
            release.wait(5)
            return httpx.Response(200, content=body)

        server = serve(slow)
        try:
            started = time.monotonic()
            first = get_limits_table()
            assert time.monotonic() - started < 1
            assert first.origin.source == "bundled"
            assert entered.wait(5)
            # In flight: further calls neither wait nor start another fetch,
            # even once the window is due again.
            limits_source._remote[URL].last_attempt = -1e9
            started = time.monotonic()
            for _ in range(5):
                assert get_limits_table().origin.source == "bundled"
            assert time.monotonic() - started < 1
            assert server.calls == 1
        finally:
            release.set()
        deadline = time.monotonic() + 5
        while limits_source._lock.locked() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert get_limits_table(refresh=False).origin.source == "remote"
        assert _azure_images() == 7


class TestDisabled:
    def test_empty_url_never_fetches(
        self, serve: Callable[..., _Server], monkeypatch: MonkeyPatch
    ) -> None:
        server = serve(_json_response(_remote_data()))
        monkeypatch.setenv(limits_source.LIMITS_URL_ENV, "")

        assert _azure_images() == 50
        origin = get_limits_table().origin
        assert origin.source == "bundled"
        assert origin.location == str(BUNDLED)
        assert server.calls == 0


class TestOverrideFileWins:
    def test_override_replaces_the_remote_provider_entry(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        serve(_json_response(_remote_data(azure_images=7)))
        override = {
            "_meta": {"schema_version": 1},
            "providers": {
                "azure": {
                    **_bundled_data()["providers"]["azure"],
                    "defaults": {
                        "max_images_per_request": {
                            "value": 10,
                            "confidence": "unverified",
                            "source": "POLICY",
                        }
                    },
                    "model_overrides": [],
                }
            },
        }
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

        table = get_limits_table()
        assert _azure_images() == 10
        assert table.providers["azure"].layer == "override"
        assert table.providers["openai"].layer == "shipped"
        assert table.origin.source == "remote"
        assert table.origin.override_file == str(path)

    def test_override_is_reapplied_after_a_refresh(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        override = {"_meta": {"schema_version": 1}, "providers": {}}
        override["providers"]["openai"] = copy.deepcopy(
            _bundled_data()["providers"]["openai"]
        )
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))
        assert _azure_images() == 7

        server.handler = _json_response(_remote_data(azure_images=9))
        clock.now += 3600
        assert _azure_images() == 9
        assert get_limits_table().providers["openai"].layer == "override"


class TestNoRefreshRead:
    """``get_limits_table(refresh=False)`` never fetches (request paths)."""

    def test_never_fetches_and_serves_bundled_before_any_fetch(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        table = get_limits_table(refresh=False)
        assert server.calls == 0
        assert table.origin.source == "bundled"

    def test_serves_the_last_good_remote_copy_without_refreshing(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        server = serve(_json_response(_remote_data(azure_images=7)))
        get_limits_table()  # a worker-style read fetches once
        clock.now += 7200  # the window is due again
        table = get_limits_table(refresh=False)
        assert server.calls == 1
        assert table.origin.source == "remote"

    def test_override_file_still_applies(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        monkeypatch: MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        serve(_json_response(_remote_data()))
        override = {
            "_meta": {"schema_version": 1},
            "providers": {
                "azure": {
                    **_bundled_data()["providers"]["azure"],
                    "defaults": {
                        "max_images_per_request": {
                            "value": 3,
                            "confidence": "unverified",
                            "source": "POLICY",
                        }
                    },
                    "model_overrides": [],
                }
            },
        }
        path = tmp_path / "override.json"
        path.write_text(json.dumps(override))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))
        table = get_limits_table(refresh=False)
        limits = resolve_image_limits("azure", "azure/my-dep", table=table)
        assert limits.max_images_per_request.value == 3
