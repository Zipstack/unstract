"""Guard: dev essentials compose must declare unstract-network when run alone."""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
ESSENTIALS_COMPOSE = REPO_ROOT / "docker" / "docker-compose-dev-essentials.yaml"
EXPECTED_NETWORK = "unstract-network"


def test_dev_essentials_compose_declares_unstract_network():
    doc = yaml.safe_load(ESSENTIALS_COMPOSE.read_text())
    networks = doc.get("networks") or {}
    default = networks.get("default") or {}
    assert default.get("name") == EXPECTED_NETWORK


def test_dev_essentials_traefik_targets_unstract_network():
    doc = yaml.safe_load(ESSENTIALS_COMPOSE.read_text())
    command = doc["services"]["reverse-proxy"]["command"]
    if isinstance(command, list):
        joined = " ".join(command)
    else:
        joined = str(command)
    assert f"--providers.docker.network={EXPECTED_NETWORK}" in joined
