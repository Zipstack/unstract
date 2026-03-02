"""Phase 6A Sanity — Plugin loader infrastructure + queue-per-executor routing.

Verifies:
1. ExecutorPluginLoader.get() returns None when no plugins installed
2. ExecutorPluginLoader.discover_executors() returns empty when no cloud executors
3. ExecutorPluginLoader.clear() resets cached state
4. ExecutorPluginLoader.get() discovers entry-point-based plugins (mocked)
5. ExecutorPluginLoader.discover_executors() loads cloud executors (mocked)
6. text_processor.add_hex_line_numbers()
7. ExecutionDispatcher._get_queue() naming convention
8. Protocol classes importable and runtime-checkable
9. executors/__init__.py triggers discover_executors()
"""

from unittest.mock import MagicMock, patch

import pytest
from executor.executors.plugins.loader import ExecutorPluginLoader
from executor.executors.plugins.text_processor import add_hex_line_numbers
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher


@pytest.fixture(autouse=True)
def _reset_plugin_loader():
    """Ensure clean plugin loader state for every test."""
    ExecutorPluginLoader.clear()
    yield
    ExecutorPluginLoader.clear()


# ── 1. Plugin loader: no plugins installed ──────────────────────────


class TestPluginLoaderNoPlugins:
    """When no cloud plugins are installed, loader returns None / empty."""

    def test_get_returns_none_for_unknown_plugin(self):
        result = ExecutorPluginLoader.get("nonexistent-plugin")
        assert result is None

    def test_get_returns_none_for_highlight_data(self):
        """highlight-data is a cloud plugin, not installed in OSS."""
        result = ExecutorPluginLoader.get("highlight-data")
        assert result is None

    def test_get_returns_none_for_challenge(self):
        result = ExecutorPluginLoader.get("challenge")
        assert result is None

    def test_get_returns_none_for_evaluation(self):
        result = ExecutorPluginLoader.get("evaluation")
        assert result is None

    def test_discover_executors_returns_empty(self):
        discovered = ExecutorPluginLoader.discover_executors()
        assert discovered == []


# ── 2. Plugin loader: clear resets cached state ─────────────────────


class TestPluginLoaderClear:
    def test_clear_resets_plugins(self):
        # Force discovery (caches empty dict)
        ExecutorPluginLoader.get("anything")
        assert ExecutorPluginLoader._plugins is not None

        ExecutorPluginLoader.clear()
        assert ExecutorPluginLoader._plugins is None

    def test_get_after_clear_re_discovers(self):
        """After clear(), next get() re-runs discovery."""
        ExecutorPluginLoader.get("x")
        assert ExecutorPluginLoader._plugins == {}

        ExecutorPluginLoader.clear()
        assert ExecutorPluginLoader._plugins is None

        # Next get() triggers fresh discovery
        ExecutorPluginLoader.get("y")
        assert ExecutorPluginLoader._plugins is not None


# ── 3. Plugin loader with mocked entry points ──────────────────────


class TestPluginLoaderWithMockedEntryPoints:
    """Simulate cloud plugins being installed by mocking entry_points()."""

    def test_get_discovers_plugin_from_entry_point(self):
        """Mocked highlight-data entry point is loaded and cached."""

        class FakeHighlightData:
            pass

        fake_ep = MagicMock()
        fake_ep.name = "highlight-data"
        fake_ep.load.return_value = FakeHighlightData

        with patch(
            "importlib.metadata.entry_points",
            return_value=[fake_ep],
        ):
            result = ExecutorPluginLoader.get("highlight-data")

        assert result is FakeHighlightData
        fake_ep.load.assert_called_once()

    def test_get_caches_after_first_call(self):
        """Entry points are only queried once; subsequent calls use cache."""
        fake_ep = MagicMock()
        fake_ep.name = "challenge"
        fake_ep.load.return_value = type("FakeChallenge", (), {})

        with patch(
            "importlib.metadata.entry_points",
            return_value=[fake_ep],
        ) as mock_eps:
            ExecutorPluginLoader.get("challenge")
            ExecutorPluginLoader.get("challenge")  # second call

        # entry_points() called only once (first get triggers discovery)
        mock_eps.assert_called_once()

    def test_failed_plugin_load_is_skipped(self):
        """If a plugin fails to load, it's skipped without raising."""
        bad_ep = MagicMock()
        bad_ep.name = "bad-plugin"
        bad_ep.load.side_effect = ImportError("missing dep")

        good_ep = MagicMock()
        good_ep.name = "good-plugin"
        good_ep.load.return_value = type("Good", (), {})

        with patch(
            "importlib.metadata.entry_points",
            return_value=[bad_ep, good_ep],
        ):
            assert ExecutorPluginLoader.get("good-plugin") is not None
            assert ExecutorPluginLoader.get("bad-plugin") is None

    def test_discover_executors_loads_classes(self):
        """Mocked cloud executor entry points are imported."""

        class FakeTableExecutor:
            pass

        fake_ep = MagicMock()
        fake_ep.name = "table"
        fake_ep.load.return_value = FakeTableExecutor

        with patch(
            "importlib.metadata.entry_points",
            return_value=[fake_ep],
        ):
            discovered = ExecutorPluginLoader.discover_executors()

        assert discovered == ["table"]
        fake_ep.load.assert_called_once()

    def test_discover_executors_skips_failures(self):
        """Failed executor loads are skipped, successful ones returned."""
        bad_ep = MagicMock()
        bad_ep.name = "broken"
        bad_ep.load.side_effect = ImportError("nope")

        good_ep = MagicMock()
        good_ep.name = "smart_table"
        good_ep.load.return_value = type("FakeSmartTable", (), {})

        with patch(
            "importlib.metadata.entry_points",
            return_value=[bad_ep, good_ep],
        ):
            discovered = ExecutorPluginLoader.discover_executors()

        assert discovered == ["smart_table"]


# ── 4. text_processor ───────────────────────────────────────────────


class TestTextProcessor:
    def test_single_line(self):
        result = add_hex_line_numbers("hello")
        assert result == "0x0: hello"

    def test_multiple_lines(self):
        result = add_hex_line_numbers("a\nb\nc")
        assert result == "0x0: a\n0x1: b\n0x2: c"

    def test_empty_string(self):
        result = add_hex_line_numbers("")
        assert result == "0x0: "

    def test_hex_width_grows(self):
        # 17 lines → hex needs 2 digits (0x10 = 16)
        text = "\n".join(f"line{i}" for i in range(17))
        result = add_hex_line_numbers(text)
        lines = result.split("\n")
        assert lines[0].startswith("0x00: ")
        assert lines[16].startswith("0x10: ")


# ── 5. Queue-per-executor routing ───────────────────────────────────


class TestQueuePerExecutor:
    def test_get_queue_legacy(self):
        assert ExecutionDispatcher._get_queue("legacy") == "celery_executor_legacy"

    def test_get_queue_table(self):
        assert ExecutionDispatcher._get_queue("table") == "celery_executor_table"

    def test_get_queue_smart_table(self):
        assert (
            ExecutionDispatcher._get_queue("smart_table")
            == "celery_executor_smart_table"
        )

    def test_get_queue_simple_prompt_studio(self):
        assert (
            ExecutionDispatcher._get_queue("simple_prompt_studio")
            == "celery_executor_simple_prompt_studio"
        )

    def test_get_queue_agentic(self):
        assert ExecutionDispatcher._get_queue("agentic") == "celery_executor_agentic"

    def test_get_queue_arbitrary_name(self):
        """Any executor_name works — no whitelist."""
        assert (
            ExecutionDispatcher._get_queue("my_custom")
            == "celery_executor_my_custom"
        )

    def test_queue_name_enum_matches_dispatcher(self):
        """QueueName.EXECUTOR matches what dispatcher generates for 'legacy'."""
        from shared.enums.worker_enums import QueueName

        assert QueueName.EXECUTOR.value == ExecutionDispatcher._get_queue("legacy")


# ── 6. Protocol classes importable ──────────────────────────────────


class TestProtocols:
    def test_highlight_data_protocol_importable(self):
        from executor.executors.plugins.protocols import HighlightDataProtocol

        assert HighlightDataProtocol is not None

    def test_challenge_protocol_importable(self):
        from executor.executors.plugins.protocols import ChallengeProtocol

        assert ChallengeProtocol is not None

    def test_evaluation_protocol_importable(self):
        from executor.executors.plugins.protocols import EvaluationProtocol

        assert EvaluationProtocol is not None

    def test_runtime_checkable(self):
        """Protocols are @runtime_checkable — isinstance checks work."""
        from executor.executors.plugins.protocols import ChallengeProtocol

        class FakeChallenge:
            def run(self):
                pass

        assert isinstance(FakeChallenge(), ChallengeProtocol)


# ── 7. executors/__init__.py triggers discovery ─────────────────────


class TestExecutorsInit:
    def test_cloud_executors_list_exists(self):
        """executors.__init__ populates _cloud_executors (empty in OSS)."""
        import executor.executors as mod

        assert hasattr(mod, "_cloud_executors")
        # In pure OSS, no cloud executors are installed
        assert isinstance(mod._cloud_executors, list)
