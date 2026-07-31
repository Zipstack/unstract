"""Run real method bodies in the unit tier, where Django settings are absent.

Guard logic worth pinning (authorization, in-use refusal) lives in modules that
import Django at module scope, so the unit tier cannot import them. Rather than
restate the logic in a test -- which passes no matter what the real code does --
these helpers slice the definition out of the source file and ``exec`` it
against stubbed collaborators, so the assertions run against the shipped body.

The end-to-end request cycle needs a database and belongs in the integration
tier; ``backend/conftest.py`` auto-marks those.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest


def extract_defs(
    module: Path, markers: tuple[str, ...], stops: tuple[str, ...]
) -> list[str]:
    """Slice each named definition out of ``module``'s source.

    Each marker is the definition's opening line, verbatim; the slice runs to
    the first ``stops`` needle after it. ``pytest.fail`` on a missing marker
    rather than skipping: a rename must break loudly, since a silently-skipped
    guard test is worse than none.
    """
    source = module.read_text()
    parts = []
    for marker in markers:
        if marker not in source:
            pytest.fail(
                f"Could not find {marker!r} in {module}. If it was renamed or "
                "inlined, update this test rather than deleting it."
            )
        start = source.index(marker)
        rest = source[start + len(marker) :]
        end = len(rest)
        for needle in stops:
            found = rest.find(needle)
            if found != -1:
                end = min(end, found)
        parts.append(marker + rest[:end])
    return parts


def exec_def(module: Path, marker: str, stops: tuple[str, ...], namespace: Any) -> Any:
    """Extract one definition, ``exec`` it in ``namespace``, and hand it back.

    The body is dedented so a method can be executed at module level, which is
    what lets a view method be driven without standing up the class.
    """
    (body,) = extract_defs(module, (marker,), stops)
    exec(compile(textwrap.dedent(body), str(module), "exec"), namespace)
    return namespace
