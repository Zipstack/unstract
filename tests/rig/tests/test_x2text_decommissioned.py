"""x2text-service is decommissioned and must not be shipped or built.

The service was a bare HTTP proxy in front of unstructured.io, used only by
the ``unstructured_community`` and ``unstructured_enterprise`` adapters. Both
are sunset and nothing else routes through it, so it is no longer deployed —
which only holds if it is gone from every file that would stand it up.

The directory, its Dockerfile and the two adapters are a separate cleanup:
removing those strands configured ``AdapterInstance`` rows, which makes it a
migration decision rather than a packaging one.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

# Files that would deploy, build or publish the service.
SHIPPING_FILES = [
    "docker/docker-compose.yaml",
    "docker/docker-compose.build.yaml",
    "docker/sample.compose.override.yaml",
    ".github/workflows/production-build.yaml",
    ".github/workflows/ci-test.yaml",
]


@pytest.mark.parametrize("relative_path", SHIPPING_FILES)
def test_service_is_not_shipped(relative_path):
    path = REPO_ROOT / relative_path
    assert path.exists(), f"{relative_path} moved — update this list"
    assert "x2text-service" not in path.read_text(), (
        f"{relative_path} still stands up or publishes x2text-service"
    )


def test_port_3004_is_not_published():
    compose = (REPO_ROOT / "docker/docker-compose.yaml").read_text()
    assert "3004" not in compose
