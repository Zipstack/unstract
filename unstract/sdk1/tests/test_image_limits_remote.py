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
from unstract.sdk1.utils.image_limits import resolve as resolve_mod
from unstract.sdk1.utils.image_limits import source as limits_source
from unstract.sdk1.utils.image_limits._schema import LimitsTable, parse_limits_bytes

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


def _remote_table(data: dict) -> LimitsTable:
    """A remote copy as the refresh would hold it (schema-checked only)."""
    return parse_limits_bytes(json.dumps(data).encode(), source="remote", location=URL)


def _clamp_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and "remote limits table loosens" in r.getMessage()
    ]


class TestRemoteMissingProvider:
    """A provider the remote copy lacks resolves from the bundled entry (O2).

    The table itself is accepted (rejecting it would also hold back every
    other fix in the file); the lookup falls back per provider.
    """

    # Providers nothing inherits from (dropping an inherit target is already
    # a schema error).
    @pytest.mark.parametrize("key", ["bedrock", "azure_ai", "minimax"])
    def test_table_is_used_and_the_provider_resolves_from_bundled(
        self, serve: Callable[..., _Server], clock: _FakeClock, key: str
    ) -> None:
        serve(_json_response(_drop_provider(key)()))

        table = get_limits_table()
        assert table.origin.source == "remote"
        assert key not in table.providers
        assert _azure_images() == 7  # the rest of the remote copy applies
        limits = resolve_image_limits(key, f"{key}/some-model", table=table)
        assert limits.is_default_provider is False
        assert limits.provider_kind == "hosted"
        assert limits.max_images_per_request.advisory is False

    def test_resolution_falls_back_to_the_bundled_entry(self) -> None:
        limits = resolve_image_limits(
            "bedrock",
            "bedrock/anthropic.claude-sonnet-4-5-v1:0",
            table=_remote_table(_drop_provider("bedrock")()),
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


def _field(value: int, *, base64_counted: bool | None = None) -> dict:
    entry: dict = {"value": value, "confidence": "verified", "source": "POLICY"}
    if base64_counted is not None:
        entry["base64_counted"] = base64_counted
    return entry


def _shadow(
    provider: str, pattern: str, *, inherit: str | None = None, **fields: dict
) -> Callable[[dict], None]:
    """Insert a NEW first override for ``pattern`` (it shadows later ones)."""

    def mutate(data: dict) -> None:
        override: dict = {"pattern": pattern, **fields}
        if inherit is not None:
            override["inherit"] = inherit
        data["providers"][provider].setdefault("model_overrides", []).insert(0, override)

    return mutate


def _add_provider(data: dict) -> None:
    entry = copy.deepcopy(data["providers"]["openai"])
    entry["adapter"] = "newco"
    entry["display_name"] = "NewCo"
    entry["defaults"]["max_images_per_request"]["value"] = 5000
    data["providers"]["newco"] = entry


def _drop_bedrock_nova2(data: dict) -> None:
    # nova-2 is held to 5 images; without its override it would get 20.
    overrides = data["providers"]["bedrock"]["model_overrides"]
    assert overrides[0]["pattern"] == "(?i)nova-2"
    del overrides[0]


BEDROCK_CLAUDE = "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"
# Index of the bundled bedrock ``(?i)claude-`` override (20 images, 20 MB).
_BEDROCK_CLAUDE_OVERRIDE = 2


def _bedrock_images() -> int | None:
    return resolve_image_limits(
        "bedrock", BEDROCK_CLAUDE, table=get_limits_table()
    ).max_images_per_request.value


class TestRemoteIsClampedAtLookup:
    """What a remote copy may change, enforced per lookup (O2, UN-4427).

    User decision: a provider's ``kind`` is locked to the bundled one, and
    an image-count or request-byte limit may rise to at most 2x the bundled
    value for the same model. Clamping each lookup (not rejecting the
    table) also catches a new override that shadows a model the bundled
    file never lists, and never freezes an install out of later fixes.
    """

    # The adversarial verifier's four shadowing cases: (mutation, provider,
    # model, field, bundled value, remote value).
    _SHADOWS = {
        "anthropic sonnet-4-5 100 -> 600": (
            _shadow(
                "anthropic",
                "(?i)claude-sonnet-4-5",
                max_images_per_request=_field(600),
            ),
            "anthropic",
            "anthropic/claude-sonnet-4-5-20250929",
            "max_images_per_request",
            100,
            600,
        ),
        "bedrock opus-4-6 inherits anthropic 20 -> 600": (
            _shadow("bedrock", "(?i)claude-opus-4-6", inherit="anthropic"),
            "bedrock",
            "bedrock/anthropic.claude-opus-4-6-v1:0",
            "max_images_per_request",
            20,
            600,
        ),
        "openrouter anthropic shadow inherits openai 100 -> 1500": (
            _shadow("openrouter", "(?i)^(openrouter/)?~?anthropic/", inherit="openai"),
            "openrouter",
            "openrouter/anthropic/claude-3.5-sonnet",
            "max_images_per_request",
            100,
            1500,
        ),
        "bedrock_mantle haiku-4-5 100 -> 600": (
            _shadow(
                "bedrock_mantle",
                "(?i)anthropic\\.claude-haiku-4-5",
                max_images_per_request=_field(600),
            ),
            "bedrock",
            "bedrock_mantle/anthropic.claude-haiku-4-5",
            "max_images_per_request",
            100,
            600,
        ),
    }

    @pytest.mark.parametrize("name", sorted(_SHADOWS))
    def test_shadowing_override_is_clamped_to_twice_bundled(
        self, caplog: pytest.LogCaptureFixture, name: str
    ) -> None:
        mutate, provider, model, field, bundled_value, remote_value = self._SHADOWS[name]
        table = _remote_table(_mutated(mutate))
        unclamped = resolve_mod._resolve_on(
            table, provider, model, cost_model=None, extra_model_ids=()
        )
        assert unclamped.field(field).value == remote_value  # the raise is real

        limits = resolve_image_limits(provider, model, table=table)
        value = limits.field(field)
        assert value.value == 2 * bundled_value
        assert value.clamped is True
        assert value.clamped_from == remote_value
        assert value.advisory is False
        assert value.confidence == "unverified"
        assert any(
            str(bundled_value) in line and str(remote_value) in line and field in line
            for line in _clamp_warnings(caplog)
        )

    def test_bedrock_opus_shadow_keeps_request_bytes_within_twice_bundled(
        self,
    ) -> None:
        # 20 MB (base64-counted) bundled vs anthropic's 32 MB: 1.6x, kept.
        mutate = self._SHADOWS["bedrock opus-4-6 inherits anthropic 20 -> 600"][0]
        limits = resolve_image_limits(
            "bedrock",
            "bedrock/anthropic.claude-opus-4-6-v1:0",
            table=_remote_table(_mutated(mutate)),
        )
        assert limits.max_request_bytes.value == 32_000_000
        assert limits.max_request_bytes.clamped is False

    _CLAMPED = {
        "bedrock defaults 20 -> 999 images": (
            _set("bedrock", "max_images_per_request", 999),
            "bedrock/meta.llama3-2-11b-instruct-v1:0",
            40,
        ),
        "bedrock defaults 20 -> 41 images": (
            _set("bedrock", "max_images_per_request", 41),
            "bedrock/meta.llama3-2-11b-instruct-v1:0",
            40,
        ),
        "table default 20 -> 999 (hosted fallback)": (
            lambda data: data["default"]["max_images_per_request"].__setitem__(
                "value", 999
            ),
            "bedrock_mantle/xai.grok-4.6",
            40,
        ),
        "removed nova-2 override loosens 5 -> 20": (
            _drop_bedrock_nova2,
            "bedrock/amazon.nova-2-lite-v1:0",
            10,
        ),
    }

    @pytest.mark.parametrize("name", sorted(_CLAMPED))
    def test_raise_past_twice_bundled_is_clamped(self, name: str) -> None:
        mutate, model, expected = self._CLAMPED[name]
        limits = resolve_image_limits(
            "bedrock", model, table=_remote_table(_mutated(mutate))
        )
        assert limits.max_images_per_request.value == expected
        assert limits.max_images_per_request.clamped is True

    @pytest.mark.parametrize(("value", "clamped"), [(30, False), (40, False), (41, True)])
    def test_raise_up_to_twice_bundled_passes(self, value: int, clamped: bool) -> None:
        mutate = _set(
            "bedrock", "max_images_per_request", value, override=_BEDROCK_CLAUDE_OVERRIDE
        )
        limits = resolve_image_limits(
            "bedrock", BEDROCK_CLAUDE, table=_remote_table(_mutated(mutate))
        )
        assert limits.max_images_per_request.value == (40 if clamped else value)
        assert limits.max_images_per_request.clamped is clamped

    def test_tightening_passes(self) -> None:
        table = _remote_table(_mutated(_set("openai", "max_images_per_request", 1)))
        limits = resolve_image_limits("openai", "gpt-4.1", table=table)
        assert limits.max_images_per_request.value == 1
        assert limits.max_images_per_request.clamped is False

    def test_kind_flip_to_pass_through_resolves_hosted(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        table = _remote_table(_mutated(_set_kind("bedrock", "pass_through")))
        limits = resolve_image_limits(
            "bedrock", "bedrock/meta.llama3-2-11b-instruct-v1:0", table=table
        )
        assert limits.provider_kind == "hosted"
        # Default-filled request bytes follow the bundled kind: enforced.
        assert limits.max_request_bytes.from_default is True
        assert limits.max_request_bytes.advisory is False
        assert limits.max_request_bytes.clamped is False  # 20 MB both sides
        assert limits.tokens_per_image.from_default is True
        assert limits.tokens_per_image.advisory is False
        assert any("kind" in line for line in _clamp_warnings(caplog))

    def test_kind_flip_to_hosted_resolves_pass_through(self) -> None:
        table = _remote_table(_mutated(_set_kind("ollama", "hosted")))
        limits = resolve_image_limits("ollama", "ollama_chat/llava", table=table)
        assert limits.provider_kind == "pass_through"
        assert limits.max_images_per_request.from_default is True
        assert limits.max_images_per_request.advisory is True

    def test_provider_unknown_to_bundled_uses_remote_data(self) -> None:
        limits = resolve_image_limits(
            "newco", "newco/vision-1", table=_remote_table(_mutated(_add_provider))
        )
        assert limits.is_default_provider is False
        assert limits.provider_kind == "hosted"
        assert limits.max_images_per_request.value == 5000
        assert limits.max_images_per_request.clamped is False

    @pytest.mark.parametrize(
        ("value", "base64_counted", "clamped"),
        [
            # bundled: 20 MB base64-counted = 15 MB raw; ceiling 30 MB raw.
            (40_000_000, True, False),  # 30 MB raw: exactly 2x
            (30_000_000, False, False),  # 30 MB raw: exactly 2x
            (40_000_000, False, True),  # 40 MB raw: same number, 2.67x
            (30_000_001, False, True),
        ],
    )
    def test_request_bytes_compare_as_raw_bytes(
        self, value: int, base64_counted: bool, clamped: bool
    ) -> None:
        def mutate(data: dict) -> None:
            data["providers"]["bedrock"]["model_overrides"][_BEDROCK_CLAUDE_OVERRIDE][
                "max_request_bytes"
            ] = _field(value, base64_counted=base64_counted)

        limits = resolve_image_limits(
            "bedrock", BEDROCK_CLAUDE, table=_remote_table(_mutated(mutate))
        )
        request = limits.max_request_bytes
        assert request.clamped is clamped
        if clamped:
            # Twice the bundled value, in the bundled value's counting.
            assert (request.value, request.base64_counted) == (40_000_000, True)
            assert request.clamped_from == value
        else:
            assert (request.value, request.base64_counted) == (value, base64_counted)

    def test_bundled_table_is_never_clamped(self) -> None:
        from unstract.sdk1.utils.image_limits.source import bundled_table

        limits = resolve_image_limits("bedrock", BEDROCK_CLAUDE, table=bundled_table())
        assert limits.max_images_per_request.clamped is False

    def test_clamp_is_logged_once_per_provider_model_field(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        table = _remote_table(
            _mutated(
                _set(
                    "bedrock",
                    "max_images_per_request",
                    999,
                    override=_BEDROCK_CLAUDE_OVERRIDE,
                )
            )
        )
        for _ in range(3):
            resolve_image_limits("bedrock", BEDROCK_CLAUDE, table=table)
        assert len(_clamp_warnings(caplog)) == 1
        resolve_image_limits(
            "bedrock", "bedrock/anthropic.claude-3-haiku-v1:0", table=table
        )
        assert len(_clamp_warnings(caplog)) == 2

    def test_message_says_the_value_was_capped(self) -> None:
        table = _remote_table(_mutated(_set("bedrock", "max_images_per_request", 999)))
        limits = resolve_image_limits(
            "bedrock", "bedrock/meta.llama3-2-11b-instruct-v1:0", table=table
        )
        text = format_limit_source(limits.max_images_per_request, limits)
        assert "capped at 2x" in text and "999" in text


class TestOldInstallKeepsGettingFixes:
    """A >2x raise for one model never holds back the rest of the file."""

    def test_tightening_applies_and_the_raise_is_clamped(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        def mutate(data: dict) -> None:
            _set(
                "bedrock",
                "max_images_per_request",
                999,
                override=_BEDROCK_CLAUDE_OVERRIDE,
            )(data)
            _set("openai", "max_images_per_request", 1)(data)

        serve(_json_response(_mutated(mutate)))
        table = get_limits_table()
        assert table.origin.source == "remote"
        assert _azure_images() == 7
        assert resolve_image_limits("openai", "gpt-4.1").max_images_per_request.value == 1
        assert _bedrock_images() == 40


class TestEveryEntryPointIsClamped:
    """Sibling sweep: all lookups go through the clamp, refresh or not."""

    BEDROCK_ID = "bedrock|8d18571f-5e96-4505-bd28-ad0379c64064"
    BEDROCK_META = {
        "model": "anthropic.claude-sonnet-4-5-20250929-v1:0",
        "aws_region_name": "us-east-1",
    }

    def test_all_entry_points(
        self, serve: Callable[..., _Server], clock: _FakeClock
    ) -> None:
        from unstract.sdk1.llm import LLM
        from unstract.sdk1.utils.image_limits import resolve_image_limits_for_adapter

        serve(
            _json_response(
                _mutated(
                    _set(
                        "bedrock",
                        "max_images_per_request",
                        999,
                        override=_BEDROCK_CLAUDE_OVERRIDE,
                    )
                )
            )
        )
        assert get_limits_table().origin.source == "remote"
        meta = dict(self.BEDROCK_META)
        results = [
            _bedrock_images(),
            resolve_image_limits("bedrock", BEDROCK_CLAUDE).max_images_per_request.value,
            resolve_image_limits_for_adapter(
                self.BEDROCK_ID, meta
            ).max_images_per_request.value,
            LLM(adapter_id=self.BEDROCK_ID, adapter_metadata=dict(meta))
            .get_image_request_limits()
            .max_images_per_request.value,
            LLM.image_input_limits_for(self.BEDROCK_ID, meta, refresh_table=False)[
                0
            ].max_images_per_request.value,
            resolve_image_limits(
                "bedrock", BEDROCK_CLAUDE, table=get_limits_table(refresh=False)
            ).max_images_per_request.value,
        ]
        assert results == [40] * len(results)


class TestOverrideFileIsNotClamped:
    """The operator's own file is configuration: it may loosen (O2)."""

    def _write(self, tmp_path: Path, monkeypatch: MonkeyPatch, data: dict) -> None:
        path = tmp_path / "override.json"
        path.write_text(json.dumps({"_meta": {"schema_version": 1}, **data}))
        monkeypatch.setenv(LIMITS_OVERRIDE_FILE_ENV, str(path))

    def test_override_file_may_raise_limits(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        serve(_json_response(_remote_data(azure_images=7)))
        bedrock = copy.deepcopy(_bundled_data()["providers"]["bedrock"])
        for override in bedrock["model_overrides"]:
            override.pop("max_images_per_request", None)
        bedrock["defaults"]["max_images_per_request"]["value"] = 999
        self._write(tmp_path, monkeypatch, {"providers": {"bedrock": bedrock}})
        assert _bedrock_images() == 999
        assert get_limits_table().origin.source == "remote"

    def test_override_file_may_flip_a_kind(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        serve(_json_response(_remote_data()))
        bedrock = copy.deepcopy(_bundled_data()["providers"]["bedrock"])
        bedrock["kind"] = "pass_through"
        self._write(tmp_path, monkeypatch, {"providers": {"bedrock": bedrock}})
        limits = resolve_image_limits(
            "bedrock", "bedrock/meta.llama3-2-11b-instruct-v1:0", table=get_limits_table()
        )
        assert limits.provider_kind == "pass_through"
        assert limits.max_request_bytes.advisory is True

    def test_override_default_may_raise(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        serve(_json_response(_remote_data()))
        self._write(
            tmp_path,
            monkeypatch,
            {
                "sources": {"OPS": {"url": "https://ops.example/limits"}},
                "default": {
                    "max_images_per_request": {
                        "value": 999,
                        "confidence": "unverified",
                        "source": "OPS",
                    }
                },
            },
        )
        limits = resolve_image_limits(
            "bedrock_mantle", "xai.grok-4.6", table=get_limits_table()
        )
        assert limits.max_images_per_request.value == 999
        assert limits.max_images_per_request.clamped is False

    def test_remote_fields_under_an_override_are_still_clamped(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        # The override replaces openai; the remote bedrock entry (raised past
        # 2x) is untouched by it, so it is still clamped.
        serve(
            _json_response(
                _mutated(
                    _set(
                        "bedrock",
                        "max_images_per_request",
                        999,
                        override=_BEDROCK_CLAUDE_OVERRIDE,
                    )
                )
            )
        )
        openai = copy.deepcopy(_bundled_data()["providers"]["openai"])
        self._write(tmp_path, monkeypatch, {"providers": {"openai": openai}})
        assert get_limits_table().providers["openai"].layer == "override"
        assert _bedrock_images() == 40

    def test_inherited_operator_fields_pass_and_remote_fields_clamp(
        self,
        serve: Callable[..., _Server],
        clock: _FakeClock,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
    ) -> None:
        # Remote: a new bedrock override inheriting anthropic, with its own
        # 999 MB request bytes. Operator: anthropic raised to 999 images.
        serve(
            _json_response(
                _mutated(
                    _shadow(
                        "bedrock",
                        "(?i)claude-opus-4-6",
                        inherit="anthropic",
                        max_request_bytes=_field(999_000_000),
                    )
                )
            )
        )
        anthropic = copy.deepcopy(_bundled_data()["providers"]["anthropic"])
        anthropic["defaults"]["max_images_per_request"]["value"] = 999
        self._write(tmp_path, monkeypatch, {"providers": {"anthropic": anthropic}})
        limits = resolve_image_limits(
            "bedrock", "bedrock/anthropic.claude-opus-4-6-v1:0", table=get_limits_table()
        )
        # Inherited from the operator's anthropic entry: not clamped.
        assert limits.max_images_per_request.layer == "override"
        assert limits.max_images_per_request.value == 999
        # The remote override's own field: clamped to 2x bundled (20 MB).
        assert limits.max_request_bytes.layer == "shipped"
        assert limits.max_request_bytes.value == 40_000_000
        assert limits.max_request_bytes.clamped is True


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
