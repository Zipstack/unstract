#!/bin/bash
# Thin wrapper around `python -m tests.rig report combine`.
#
# Kept for backward compatibility with any external script or local workflow
# that still invokes this path. Prefer calling the rig directly.
set -euo pipefail

REPORTS_DIR="${REPORTS_DIR:-reports}"

if command -v python >/dev/null 2>&1; then
    python -m tests.rig report combine --reports-dir "$REPORTS_DIR"
fi

# Backward-compatible alias for the existing sticky-comment step which uploads
# combined-test-report.md from the repo root.
if [ -f "$REPORTS_DIR/combined-test-report.md" ] && [ ! -f combined-test-report.md ]; then
    cp "$REPORTS_DIR/combined-test-report.md" combined-test-report.md
fi
