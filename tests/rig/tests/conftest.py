"""Pytest config for rig self-tests.

The rig's path validation in :func:`tests.rig.groups._validate_paths` asserts
that every non-optional group's workdir + paths exist on disk. The self-test
fixtures construct synthetic manifests pointing at temp directories, so we
bypass path validation by always marking synthetic groups as ``optional`` (or
by creating the directories the test references).
"""

import pytest

from tests.rig.groups import EXTRA_MANIFESTS_ENV


@pytest.fixture(autouse=True)
def _no_inherited_extra_manifests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the runner's overlay manifests out of the synthetic ones.

    Cloud CI exports UNSTRACT_RIG_EXTRA_MANIFESTS for the whole job, and
    load_groups() merges it into whatever DEFAULT_MANIFEST a test patched in.
    An overlay group that depends on an OSS group (every `requires_platform`
    one depends on `e2e-smoke`) then fails validation against a synthetic
    manifest that never defines it. Tests that exercise overlays set the
    variable themselves.
    """
    monkeypatch.delenv(EXTRA_MANIFESTS_ENV, raising=False)
