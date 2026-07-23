import importlib
import sys

import pytest
from unstract.core.plugins.plugin_manager import PluginManager


def _write_plugin(plugins_pkg_dir, plugin_name, metadata_body):
    plugin_dir = plugins_pkg_dir / plugin_name
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text(f"metadata = {metadata_body}\n")


@pytest.fixture
def plugins_pkg_dir(tmp_path, monkeypatch):
    """Create an importable package directory to hold fake plugins."""
    pkg_dir = tmp_path / "fake_plugins_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    yield pkg_dir

    sys.modules.pop("fake_plugins_pkg", None)
    for name in list(sys.modules):
        if name.startswith("fake_plugins_pkg."):
            sys.modules.pop(name)


def _load(plugins_pkg_dir):
    manager = PluginManager(
        plugins_dir=plugins_pkg_dir,
        plugins_pkg="fake_plugins_pkg",
        use_singleton=False,
    )
    manager.load_plugins()
    return manager


def test_known_and_unknown_class_fields_are_both_registered(plugins_pkg_dir):
    """A plugin's *_class/*_cls metadata fields should surface on the plugin dict,
    including fields the loader has never seen before (e.g. headers_cache_class) -
    not just the historically hardcoded entrypoint_cls/exception_cls/service_class.
    """
    _write_plugin(
        plugins_pkg_dir,
        "sample_plugin",
        '{"name": "sample_plugin", "service_class": str, "headers_cache_class": dict, }',
    )

    plugin = _load(plugins_pkg_dir).get_plugin("sample_plugin")

    assert plugin["service_class"] is str
    assert plugin["headers_cache_class"] is dict
    assert plugin["metadata"]["name"] == "sample_plugin"


def test_entrypoint_and_exception_cls_still_supported(plugins_pkg_dir):
    _write_plugin(
        plugins_pkg_dir,
        "sample_plugin",
        '{"name": "sample_plugin", "entrypoint_cls": int, "exception_cls": ValueError, }',
    )

    plugin = _load(plugins_pkg_dir).get_plugin("sample_plugin")

    assert plugin["entrypoint_cls"] is int
    assert plugin["exception_cls"] is ValueError


def test_non_class_metadata_fields_are_not_duplicated_at_top_level(plugins_pkg_dir):
    _write_plugin(
        plugins_pkg_dir,
        "sample_plugin",
        '{"name": "sample_plugin", "description": "just a description", }',
    )

    plugin = _load(plugins_pkg_dir).get_plugin("sample_plugin")

    assert "description" not in plugin
    assert plugin["metadata"]["description"] == "just a description"


def test_disabled_plugin_is_not_loaded(plugins_pkg_dir):
    _write_plugin(
        plugins_pkg_dir,
        "sample_plugin",
        '{"name": "sample_plugin", "disable": True}',
    )

    manager = _load(plugins_pkg_dir)

    assert not manager.has_plugin("sample_plugin")
