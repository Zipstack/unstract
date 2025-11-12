"""Pytest configuration for integration tests.

This module loads environment variables from .env.test before test collection
and ensures the integration tests directory is in the Python path for imports.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Add the integration tests directory to Python path for test config imports
integration_dir = Path(__file__).parent
if str(integration_dir) not in sys.path:
    sys.path.insert(0, str(integration_dir))

# Load .env.test file from the integration tests directory
env_file = integration_dir / ".env.test"
if env_file.exists():
    load_dotenv(env_file)
