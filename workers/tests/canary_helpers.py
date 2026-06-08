"""Shared AST-walk helpers for inventory-style canary tests.

Several test files audit the production code tree (forbid a raw
dispatch, require a kwarg, etc.). The file-walking + parse-with-skip
logic is identical across them; this module is the single home.
"""

from __future__ import annotations

import ast
import pathlib
import warnings

WORKERS_ROOT = pathlib.Path(__file__).parent.parent

# Always-skip top-level directories. Callers pass a wider set if they
# need to additionally exclude e.g. the seam module itself.
DEFAULT_SKIP_TOP_DIRS = frozenset({"tests", "__pycache__", "htmlcov", ".venv"})


def iter_production_trees(
    skip_top_dirs: frozenset[str] = DEFAULT_SKIP_TOP_DIRS,
) -> list[tuple[pathlib.Path, ast.AST]]:
    """Return a list of ``(rel_path, parsed_tree)`` tuples for every
    .py file outside the skip set.

    Unparseable files emit a ``UserWarning`` and are skipped — silent
    skipping would let canaries pass vacuously on a botched merge.
    Tests can promote the warning to an error via
    ``warnings.simplefilter("error", UserWarning)`` if they want
    strict enforcement.
    """
    out: list[tuple[pathlib.Path, ast.AST]] = []
    for py in WORKERS_ROOT.rglob("*.py"):
        rel = py.relative_to(WORKERS_ROOT)
        if rel.parts and rel.parts[0] in skip_top_dirs:
            continue
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError as exc:
            warnings.warn(
                f"canary scan skipping unparseable file {rel}: {exc}",
                UserWarning,
                stacklevel=2,
            )
            continue
        out.append((rel, tree))
    return out
