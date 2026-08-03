"""Run real method bodies against stubbed collaborators, without the class.

These helpers slice a definition out of its source file and ``exec`` it in a
namespace of stubs, so assertions run against the shipped body rather than a
restatement of it that would pass no matter what the real code does.

**Prefer importing the module.** Django settings *are* configured in the unit
tier (``tests/groups.yaml`` sets ``DJANGO_SETTINGS_MODULE`` for
``unit-backend``), and ``backend/conftest.py`` auto-marks only ``django_db`` and
``TestCase`` tests as ``integration`` -- so a plain import plus
``unittest.mock.patch`` runs per-PR and is the established pattern here (see
``prompt_studio_core_v2/tests/test_build_index_payload.py``). Reach for these
helpers only where that genuinely will not do.

**Limitations, because they are not obvious:**

* The extracted body is not bound to its class, the URLconf, or DRF dispatch,
  so a test using it cannot tell wired code from unreachable code. Pair it with
  an explicit wiring test (``tests_common/test_route_wiring.py``).
* Names resolve from the supplied namespace, never from the module's own import
  block -- a deleted or renamed import is invisible here.
* Slicing stops at the first ``stops`` needle, so inserting a decorator above a
  definition silently truncates it and the assertions then cover a *different*
  body than ships.
* The marker must match the definition line verbatim, so a cosmetic annotation
  change breaks the match.
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


def _line_offset(source: str, marker: str) -> int:
    """0-based line on which ``marker`` starts."""
    return source.count("\n", 0, source.index(marker))


def exec_def(module: Path, marker: str, stops: tuple[str, ...], namespace: Any) -> Any:
    """Extract one definition, ``exec`` it in ``namespace``, and hand it back.

    The body is dedented so a method can be executed at module level, which is
    what lets a view method be driven without standing up the class.

    Blank lines are prepended so the snippet sits at its real line number.
    ``compile`` is given the true path, so without the padding a traceback
    would pair a genuine filename with a snippet-relative line -- pointing
    whoever debugs a failure at whatever unrelated source sits there.
    """
    (body,) = extract_defs(module, (marker,), stops)
    padding = "\n" * _line_offset(module.read_text(), marker)
    exec(compile(padding + textwrap.dedent(body), str(module), "exec"), namespace)
    return namespace
