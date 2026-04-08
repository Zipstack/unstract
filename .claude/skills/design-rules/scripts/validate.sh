#!/usr/bin/env bash
# Validate the design rules system. Run from the repo root.
#
# Checks:
#   1. No forbidden words appear in any design rule file (cloud, enterprise,
#      HITL, agentic, vendor names, unimplemented design names, etc.).
#   2. Every per-component DESIGN_RULES.md contains the verbatim compatibility
#      statement.
#   3. Every per-component DESIGN_RULES.md lives in a directory that exists
#      and contains real source (not just __pycache__).
#
# Exit codes: 0 = clean, 1 = problems found.

set -u
fail=0

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 2

echo "==> 1. Forbidden-word scan"
FORBIDDEN='cloud|enterprise|unstract-cloud|hitl|manual.review|subscription|agentic|simple.prompt.studio|public.shares|greptile|AuditLog|SoftDeleteMixin|departure workflow|GDPR|OWNER role|ManagementKey|ExecutionKey|uxm_|uxe_|deletion guard|informed deletion'

mapfile -t COMPONENT_FILES < <(find backend unstract workers -name DESIGN_RULES.md 2>/dev/null)

if grep -rEl -i "$FORBIDDEN" \
    design-rules/ "${COMPONENT_FILES[@]}" 2>/dev/null; then
  echo "    FAIL: forbidden words found in the files listed above"
  fail=1
else
  echo "    OK"
fi

echo
echo "==> 2. Compatibility statement presence"
COMPAT='All changes to this component must remain compatible'
for f in "${COMPONENT_FILES[@]}"; do
  if ! grep -q "$COMPAT" "$f"; then
    echo "    MISSING: $f"
    fail=1
  fi
done
[[ $fail -eq 0 ]] && echo "    OK"

echo
echo "==> 3. Component directory sanity"
for f in "${COMPONENT_FILES[@]}"; do
  dir="$(dirname "$f")"
  # Real source = at least one file other than DESIGN_RULES.md and __pycache__
  real=$(find "$dir" -maxdepth 1 -mindepth 1 \
    ! -name DESIGN_RULES.md ! -name __pycache__ 2>/dev/null | head -1)
  if [[ -z "$real" ]]; then
    echo "    EMPTY DIR: $f (no real source alongside)"
    fail=1
  fi
done
[[ $fail -eq 0 ]] && echo "    OK"

echo
if [[ $fail -eq 0 ]]; then
  echo "All design rule checks passed."
  exit 0
else
  echo "Design rule checks FAILED. Fix the items listed above."
  exit 1
fi
