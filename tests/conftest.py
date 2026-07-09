"""Top-level conftest for tests/ tree.

Registers shared markers and re-exports e2e fixtures so any test under
``tests/`` can ``import`` from ``tests.e2e.fixtures`` without path gymnastics.
"""

from __future__ import annotations


def pytest_configure(config) -> None:
    # Markers are also registered in the root pyproject.toml; declaring them
    # here too lets ad-hoc invocations (`pytest tests/`) succeed without
    # importing pyproject ini-options when pytest is run from a sub-workdir.
    config.addinivalue_line("markers", "unit: marks tests as unit (no external services)")
    config.addinivalue_line("markers", "integration: marks tests as integration")
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end (require platform)"
    )
    config.addinivalue_line("markers", "critical: marks tests covering a critical path")
    config.addinivalue_line("markers", "slow: marks tests as slow")
