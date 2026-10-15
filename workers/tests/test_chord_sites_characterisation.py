"""Inventory canary: no Celery ``chord(...)`` anywhere in ``workers/``.

Chord was the fan-out primitive before the PG barrier, and the highest-risk
Celery construct at our scale (silent task drops at ~130K tasks). This suite
originally characterised the two inline ``chord(header)(body)`` call sites, then
narrowed to "exactly one call site, inside ``queue_backend/barrier.py``" once
they were lifted behind the ``Barrier`` abstraction.

UN-4078 deleted that last call site along with ``CeleryChordBarrier``, so the
expected count is now **zero**. What is left is worth keeping rather than
deleting with the rest: chord is still importable from the Celery library that
the PG consumer itself is built on, so nothing at the type or import level stops
someone reintroducing one. A reintroduced chord would publish to a broker with
no consumers, and — unlike a bad PG dispatch — would fail silently, with no
``pg_barrier_state`` row for the reaper to recover from.

The behavioural characterisation tests that used to live here were deleted with
the code they mocked: they patched ``queue_backend.barrier.chord``, which no
longer exists. The fan-out contract they covered (zero batches → ``None``,
non-empty → enqueue, failures re-raise) is covered against the surviving
substrate in ``test_pg_barrier.py`` and ``test_barrier.py``.
"""

import pathlib
import re

import pytest

# Top-level directories under workers/ that are not production source.
_SKIP_TOP_DIRS = {"tests", "__pycache__", "htmlcov", ".venv"}


def _production_py_files() -> list[pathlib.Path]:
    workers_root = pathlib.Path(__file__).parent.parent
    out = []
    for py in workers_root.rglob("*.py"):
        rel_parts = py.relative_to(workers_root).parts
        if rel_parts and rel_parts[0] in _SKIP_TOP_DIRS:
            continue
        out.append(py)
    return out


def _scan(pattern: re.Pattern, *, skip_comments: bool) -> list[str]:
    workers_root = pathlib.Path(__file__).parent.parent
    hits = []
    for py in _production_py_files():
        for line_no, line in enumerate(py.read_text().splitlines(), start=1):
            if skip_comments and line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                hits.append(f"{py.relative_to(workers_root)}:{line_no}")
    return hits


class TestNoChordRemains:
    """``chord(...)`` must not reappear in production worker code."""

    def test_no_chord_invocation(self):
        """No assignment-form ``= chord(`` call anywhere in workers/.

        **Known blind spots**, unchanged from when this asserted a count of one:
        a return-value-discarded ``chord(batch)(cb)`` evades the assignment-form
        regex, and an aliased import (``from celery import chord as c``) or
        module-attribute access (``import celery`` + ``celery.chord(...)``)
        evades both this and the import canary below. Those shapes are
        non-idiomatic and appear nowhere in the tree; broaden these canaries if
        one ever ships.
        """
        hits = _scan(re.compile(r"=\s*chord\("), skip_comments=True)
        assert hits == [], (
            "Celery chord(...) call site(s) found in workers/:\n  "
            + "\n  ".join(hits)
            + "\nChord was removed with the Celery transport (UN-4078). A chord "
            "publishes to a broker that has no consumers, and fails silently — "
            "no pg_barrier_state row is written, so the reaper cannot recover "
            "the stranded execution. Fan out through "
            "WorkflowOrchestrationUtils.create_chord_execution (PgBarrier)."
        )

    def test_no_chord_import(self):
        """``from celery import chord`` must not appear in workers/."""
        hits = _scan(
            re.compile(r"^\s*from\s+celery\s+import\s+.*\bchord\b"), skip_comments=False
        )
        assert hits == [], (
            "`from celery import chord` found in workers/:\n  " + "\n  ".join(hits)
        )

    def test_scanner_sees_a_realistic_tree(self):
        """Non-vacuity lock: the scan must actually walk production files.

        Without this, a path bug (wrong root, over-broad skip list) would make
        both canaries above pass over an empty set and report all-clear forever
        — the exact failure mode a zero-expectation assertion invites.
        """
        files = _production_py_files()
        assert len(files) > 50, f"expected a populated tree, walked {len(files)} files"
        names = {f.name for f in files}
        assert "pg_barrier.py" in names
        assert "barrier.py" in names

    def test_detector_matches_a_known_bad_line(self):
        """Positive-detection lock for the invocation regex."""
        pattern = re.compile(r"=\s*chord\(")
        assert pattern.search("        result = chord(header_tasks)(callback)")
        assert not pattern.search("    # the chord(...) primitive is gone")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
