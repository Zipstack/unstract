"""Pytest plugin injected by the rig into every group's pytest run.

Copies ``@pytest.mark.critical_path("<path-id>")`` marker args into junit
testcase ``<properties>`` so the rig can attest critical-path coverage from
tests that actually passed, not just from a group's overall exit code. A test
may carry the marker multiple times (or pass several ids) to attest several
paths.

Lives in its own directory (not ``tests/rig/``) because the rig injects it via
``PYTHONPATH`` + ``-p`` into each group's own venv — putting ``tests/rig`` on
``PYTHONPATH`` would shadow real packages (e.g. ``coverage``). Stdlib-only for
the same reason.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "critical_path(path_id, ...): attests coverage of declared critical "
        "path(s) from tests/critical_paths.yaml when this test passes",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker in item.iter_markers("critical_path"):
            for path_id in marker.args:
                item.user_properties.append(("critical_path", str(path_id)))
