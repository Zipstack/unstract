#!/bin/bash
# Thin wrapper around `python3 -m tests.rig report combine`.
#
# Kept for backward compatibility with any external script or local workflow
# that still invokes this path. Prefer calling the rig directly.
set -euo pipefail

REPORTS_DIR="${REPORTS_DIR:-reports}"

# Stock Ubuntu CI runners only ship `python3`, not `python`. Pick whichever is
# on PATH; bail loudly if neither.
if command -v python3 >/dev/null 2>&1; then
    PY=python3
elif command -v python >/dev/null 2>&1; then
    PY=python
else
    echo "combine-test-reports.sh: no python interpreter on PATH" >&2
    exit 1
fi

"$PY" -m tests.rig report combine --reports-dir "$REPORTS_DIR"

# Backward-compatible alias for the existing sticky-comment step which uploads
# combined-test-report.md from the repo root.
if [ -f "$REPORTS_DIR/combined-test-report.md" ] && [ ! -f combined-test-report.md ]; then
    cp "$REPORTS_DIR/combined-test-report.md" combined-test-report.md
fi
