"""Pytest configuration for connector tests."""

from pathlib import Path

from dotenv import load_dotenv


def pytest_configure(config):
    """Load .env file before running tests."""
    # Load .env from unstract/connectors/.env
    connectors_dir = Path(__file__).parent.parent
    env_file = connectors_dir / ".env"

    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment variables from {env_file}")
    else:
        print(f"⚠ No .env file found at {env_file}")
