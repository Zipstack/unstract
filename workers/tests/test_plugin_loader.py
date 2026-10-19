"""Plugin loader infrastructure + queue-per-executor routing.

Verifies:
1. ExecutorPluginLoader.get() returns None when no plugins installed
2. ExecutorPluginLoader.discover_executors() returns empty when no cloud executors
3. ExecutorPluginLoader.clear() resets cached state
4. ExecutorPluginLoader.get() discovers entry-point-based plugins (mocked)
5. ExecutorPluginLoader.discover_executors() loads cloud executors (mocked)
6. text_processor.add_hex_line_numbers()
7. Queue-per-executor naming convention (QUEUE_PREFIX)
8. Protocol classes importable and runtime-checkable
9. executors.register_all() triggers discover_executors()
"""

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from executor.executors.plugins.loader import ExecutorPluginLoader
from executor.executors.plugins.text_processor import add_hex_line_numbers

from unstract.workflow_execution.executor_rpc import QUEUE_PREFIX


@pytest.fixture(autouse=True)
def _reset_plugin_loader():
    """Ensure clean plugin loader state for every test."""
    ExecutorPluginLoader.clear()
    yield
    ExecutorPluginLoader.clear()


# ── 1. Plugin loader: no plugins installed ──────────────────────────


class TestPluginLoaderNoPlugins:
    """When no cloud plugins are installed, loader returns None / empty.

    Mocks entry_points to simulate a clean OSS environment where
    no cloud executor plugins are pip-installed.
    """

    @patch(
        "importlib.metadata.entry_points",
        return_value=[],
    )
    def test_get_returns_none_for_unknown_plugin(self, _mock_eps):
        result = ExecutorPluginLoader.get("nonexistent-plugin")
        assert result is None

    @patch(
        "importlib.metadata.entry_points",
        return_value=[],
    )
    def test_get_returns_none_for_highlight_data(self, _mock_eps):
        """highlight-data is a cloud plugin, not installed in OSS."""
        result = ExecutorPluginLoader.get("highlight-data")
        assert result is None

    @patch(
        "importlib.metadata.entry_points",
        return_value=[],
    )
    def test_get_returns_none_for_challenge(self, _mock_eps):
        result = ExecutorPluginLoader.get("challenge")
        assert result is None

    @patch(
        "importlib.metadata.entry_points",
        return_value=[],
    )
    def test_get_returns_none_for_evaluation(self, _mock_eps):
        result = ExecutorPluginLoader.get("evaluation")
        assert result is None

    @patch(
        "importlib.metadata.entry_points",
        return_value=[],
    )
    def test_discover_executors_returns_empty(self, _mock_eps):
        discovered = ExecutorPluginLoader.discover_executors()
        assert discovered == []


# ── 2. Plugin loader: clear resets cached state ─────────────────────


class TestPluginLoaderClear:
    @patch("importlib.metadata.entry_points", return_value=[])
    def test_clear_resets_plugins(self, _mock_eps):
        # Force discovery (caches empty dict)
        ExecutorPluginLoader.get("anything")
        assert ExecutorPluginLoader._plugins is not None

        ExecutorPluginLoader.clear()
        assert ExecutorPluginLoader._plugins is None

    @patch("importlib.metadata.entry_points", return_value=[])
    def test_get_after_clear_re_discovers(self, _mock_eps):
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
    """Queue-per-executor naming, now owned solely by the PG executor RPC.

    The names are ``celery_executor_*`` for historical reasons and are NOT dead
    Celery surface: ``worker-pg-executor`` subscribes to exactly these strings
    (chart ``workerPgExecutor.env.WORKER_PG_QUEUE_CONSUMER_QUEUE``). Renaming the
    prefix without changing the chart would silently strand every tool execution,
    so these assertions pin the literal wire names rather than deriving them.
    """

    @pytest.mark.parametrize(
        "executor_name",
        ["legacy", "table", "smart_table", "simple_prompt_studio", "agentic"],
    )
    def test_queue_for_known_executor(self, executor_name):
        assert f"{QUEUE_PREFIX}{executor_name}" == f"celery_executor_{executor_name}"

    def test_queue_for_arbitrary_name(self):
        """Any executor_name works — no whitelist."""
        assert f"{QUEUE_PREFIX}my_custom" == "celery_executor_my_custom"

    def test_queue_name_enum_matches_prefix(self):
        """QueueName.EXECUTOR matches what the PG dispatcher builds for 'legacy'."""
        from shared.enums.worker_enums import QueueName

        assert QueueName.EXECUTOR.value == f"{QUEUE_PREFIX}legacy"


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
                pass  # Minimal stub to satisfy ChallengeProtocol for isinstance check

        assert isinstance(FakeChallenge(), ChallengeProtocol)


# ── 7. executors.register_all() triggers discovery ──────────────────


class TestExecutorsInit:
    """``register_all()``'s guarantees, each pinned against its own failure.

    These cases *write* process-global state — ``register_all()`` registers into
    the ``ExecutorRegistry`` singleton, and they stamp on the module's
    ``_cloud_executors`` latch — so the fixture snapshots and restores both.
    The ``sys.modules`` entry for ``legacy_executor`` is not restorable and is
    deliberately left. The sibling modules' guards are correct either way, so
    leaving it is harmless.

    No case here asserts registry *contents* off an inherited state. Registration
    is asserted in a subprocess, and the one case that needs ``legacy`` already
    present arranges that itself. That is deliberate: in-process such an
    assertion would pin whatever module ran before it rather than the code under
    test, and the repo's test rig runs these under xdist with the default
    per-test scheduler (``<repo root>/tests/rig/cli.py``), so collection order is
    not something to rely on.
    """

    @pytest.fixture(autouse=True)
    def _isolate_global_state(self):
        import executor.executors as mod

        from unstract.sdk1.execution.registry import ExecutorRegistry

        saved = dict(ExecutorRegistry._registry)
        saved_cloud = mod._cloud_executors
        yield
        # Restore exactly, including removing keys this class added — importing
        # ``legacy_executor`` registers as a side effect, and running real
        # discovery would register the cloud executors too. Leaving those behind
        # would collide with the sibling modules that register the same names
        # themselves, since duplicate registration raises. Nothing depends on
        # this class having registered ``legacy``: every consumer in the suite
        # registers it explicitly or assigns it directly.
        ExecutorRegistry._registry.clear()
        ExecutorRegistry._registry.update(saved)
        mod._cloud_executors = saved_cloud

    def test_register_all_registers_the_bundled_executor(self):
        """In a fresh process, register_all() populates the registry.

        A fresh interpreter is the only honest way to assert this: registration
        rides on importing ``legacy_executor``, so in-process the decorator has
        already fired and the assertion would pass on whatever an earlier module
        left behind rather than on the call under test. Subprocess isolation is
        the same technique ``test_executor_registration.py`` uses, and for the
        same reason.
        """
        code = (
            "from executor.executors import register_all\n"
            "from unstract.sdk1.execution.registry import ExecutorRegistry\n"
            "if ExecutorRegistry.list_executors():\n"
            "    raise SystemExit('registry pre-populated')\n"
            "register_all()\n"
            "names = ExecutorRegistry.list_executors()\n"
            "if names.count('legacy') != 1:\n"
            "    raise SystemExit(f'expected one legacy: {names}')\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "WORKER_TYPE": "executor"},
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert result.returncode == 0, (
            f"register_all() did not register in a fresh process.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_legacy_executor_resolves_through_the_package_namespace(self):
        """``from executor.executors import LegacyExecutor`` must keep working.

        The class used to be a real module attribute; it is now resolved by
        ``__getattr__``. No caller in this repo or the cloud plugins uses this
        spelling today — they import the submodule directly — so nothing else
        would catch a typo in the name comparison or the inner import path, and
        the attribute it replaced could not fail this way.
        """
        import executor.executors as mod
        from executor.executors.legacy_executor import LegacyExecutor

        assert mod.LegacyExecutor is LegacyExecutor

        with pytest.raises(AttributeError):
            mod.NoSuchExecutor

    def test_register_all_discovers_entry_points_only_once(self):
        """Idempotency, asserted on the work done rather than the value returned.

        In OSS no cloud plugins are installed, so ``register_all()`` returns
        ``[]`` on the first call as well as later ones — asserting on the return
        value cannot tell a working latch from no latch at all.
        """
        import executor.executors as mod
        from executor.executors.plugins.loader import ExecutorPluginLoader

        mod._reset_discovery_for_tests()
        with patch.object(
            ExecutorPluginLoader, "discover_executors", return_value=["fake_cloud"]
        ) as spy:
            first = mod.register_all()
            second = mod.register_all()

        assert spy.call_count == 1, f"discovery re-ran: {spy.call_count} calls"
        assert first == ["fake_cloud"]
        assert second == ["fake_cloud"], "the names must survive the latched call"

    def test_register_all_is_reentrant(self):
        """A plugin that calls back into ``register_all()`` must not restart discovery.

        ``ep.load()`` executes third-party code. If the latch were set only
        after discovery, a plugin whose import graph reaches this function would
        re-enter with discovery un-latched and loop the entry points again, once
        per level.
        """
        import executor.executors as mod
        from executor.executors.plugins.loader import ExecutorPluginLoader

        mod._reset_discovery_for_tests()
        loads = []

        def _reentrant_discovery():
            loads.append(1)
            if len(loads) < 5:
                mod.register_all()  # what a re-entrant ep.load() would do
            return ["reentrant"]

        with patch.object(
            ExecutorPluginLoader, "discover_executors", _reentrant_discovery
        ):
            mod.register_all()

        assert len(loads) == 1, f"discovery re-entered {len(loads)} times"

    def test_register_all_tolerates_legacy_executor_already_registered(self):
        """``register_all()`` must not raise when ``legacy`` is already present.

        ``ExecutorRegistry.register`` raises ``ValueError`` on a duplicate name,
        and this ordering is real: a cloud plugin imports ``LegacyExecutor`` at
        module scope and is loaded by ``ep.load()`` *inside* discovery, so the
        class can already be registered when the call reaches it.

        The precondition is arranged here rather than inherited — asserting on a
        registry state some earlier module left behind would pin that module,
        not this code. Discovery is patched for the same reason: unpatched, this
        would run real ``entry_points()`` and, where the cloud wheels are
        installed, register every cloud executor as a side effect of a test that
        is not about them.
        """
        import executor.executors as mod
        from executor.executors.legacy_executor import LegacyExecutor
        from executor.executors.plugins.loader import ExecutorPluginLoader

        from unstract.sdk1.execution.registry import ExecutorRegistry

        if "legacy" not in ExecutorRegistry.list_executors():
            ExecutorRegistry.register(LegacyExecutor)

        mod._reset_discovery_for_tests()
        with patch.object(ExecutorPluginLoader, "discover_executors", return_value=[]):
            mod.register_all()  # must not raise

        assert "legacy" in ExecutorRegistry.list_executors()

    @pytest.mark.parametrize("exc", [RuntimeError, KeyboardInterrupt, SystemExit])
    def test_failed_discovery_un_arms_the_latch(self, exc):
        """A discovery that raises must not leave ``[]`` latched.

        Otherwise every later call in the process reports "no cloud executors"
        as though discovery had succeeded, which is indistinguishable from the
        OSS case.

        Every class that reaches the handler is exercised: an ordinary
        ``Exception``, which escapes ``entry_points()`` because that call runs
        before any per-entry-point ``try``, and the ``BaseException``-not-
        ``Exception`` classes, which are the only ones that escape
        ``ep.load()``. Parametrised rather than looped so one failing arm cannot
        stop the others from running.
        """
        import executor.executors as mod
        from executor.executors.plugins.loader import ExecutorPluginLoader

        mod._reset_discovery_for_tests()
        with patch.object(
            ExecutorPluginLoader, "discover_executors", side_effect=exc("boom")
        ):
            with pytest.raises(exc):
                mod.register_all()

        assert (
            mod._cloud_executors is None
        ), f"{exc.__name__} left the latch armed: {mod._cloud_executors!r}"

    def test_register_all_returns_a_copy_callers_cannot_corrupt(self):
        """The latched list is module state; callers must not be able to edit it."""
        import executor.executors as mod
        from executor.executors.plugins.loader import ExecutorPluginLoader

        mod._reset_discovery_for_tests()
        with patch.object(
            ExecutorPluginLoader, "discover_executors", return_value=["table"]
        ):
            first = mod.register_all()

        first.append("MUTATED-BY-CALLER")
        assert mod.register_all() == ["table"]
