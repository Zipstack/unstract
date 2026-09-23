"""OSS test settings: the production base plus the shared test-only deltas.

The deltas live in `test_base` rather than here because `copy_cloud_deps`
replaces this file on a cloud build.
"""

from backend.settings.base import *  # noqa: F401, F403
from backend.settings.test_base import *  # noqa: F401, F403
