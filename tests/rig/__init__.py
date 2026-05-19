"""Unstract test rig — entry point package.

The rig is invoked as ``python -m tests.rig <subcommand>`` (see :mod:`tests.rig.cli`).
It is the single dispatcher behind ``tox`` envs, the pre-commit hook, and CI.
"""

from tests.rig.groups import GroupDefinition, GroupManifest, load_groups
from tests.rig.critical_paths import CriticalPath, CriticalPathRegistry, load_critical_paths

__all__ = [
    "GroupDefinition",
    "GroupManifest",
    "load_groups",
    "CriticalPath",
    "CriticalPathRegistry",
    "load_critical_paths",
]
