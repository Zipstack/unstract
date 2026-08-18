"""Pytest config for rig self-tests.

The rig's path validation in :func:`tests.rig.groups._validate_paths` asserts
that every non-optional group's workdir + paths exist on disk. The self-test
fixtures construct synthetic manifests pointing at temp directories, so we
bypass path validation by always marking synthetic groups as ``optional`` (or
by creating the directories the test references).
"""
