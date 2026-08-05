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
#
# Portability: bash 3.2+ (macOS default). Avoids `mapfile`/`readarray` and
# avoids expanding potentially-empty arrays under `set -u`.

set -u
fail=0

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 2

# Populate COMPONENT_FILES portably (no mapfile — bash 3.2 compatible).
COMPONENT_FILES=()
while IFS= read -r -d '' f; do
  COMPONENT_FILES+=("$f")
done < <(find backend unstract workers -name DESIGN_RULES.md -print0 2>/dev/null)

echo "==> 1. Forbidden-word scan"
FORBIDDEN='cloud|enterprise|unstract-cloud|hitl|manual.review|subscription|agentic|simple.prompt.studio|public.shares|greptile|AuditLog|SoftDeleteMixin|departure workflow|GDPR|OWNER role|ManagementKey|ExecutionKey|uxm_|uxe_|deletion guard|informed deletion'

check1_fail=0
if [[ ${#COMPONENT_FILES[@]} -gt 0 ]]; then
  if grep -rEl -i "$FORBIDDEN" \
      design-rules/ "${COMPONENT_FILES[@]}" 2>/dev/null; then
    echo "    FAIL: forbidden words found in the files listed above"
    check1_fail=1
    fail=1
  fi
else
  if grep -rEl -i "$FORBIDDEN" design-rules/ 2>/dev/null; then
    echo "    FAIL: forbidden words found in the files listed above"
    check1_fail=1
    fail=1
  fi
fi
[[ $check1_fail -eq 0 ]] && echo "    OK"

echo
echo "==> 2. Compatibility statement presence"
COMPAT='All changes to this component must remain compatible'
check2_fail=0
for f in "${COMPONENT_FILES[@]+"${COMPONENT_FILES[@]}"}"; do
  if ! grep -q "$COMPAT" "$f"; then
    echo "    MISSING: $f"
    check2_fail=1
    fail=1
  fi
done
[[ $check2_fail -eq 0 ]] && echo "    OK"

echo
echo "==> 3. Component directory sanity"
check3_fail=0
for f in "${COMPONENT_FILES[@]+"${COMPONENT_FILES[@]}"}"; do
  dir="$(dirname "$f")"
  # Real source = at least one file other than DESIGN_RULES.md and __pycache__
  real=$(find "$dir" -maxdepth 1 -mindepth 1 \
    ! -name DESIGN_RULES.md ! -name __pycache__ 2>/dev/null | head -1)
  if [[ -z "$real" ]]; then
    echo "    EMPTY DIR: $f (no real source alongside)"
    check3_fail=1
    fail=1
  fi
done
[[ $check3_fail -eq 0 ]] && echo "    OK"

echo
if [[ $fail -eq 0 ]]; then
  echo "All design rule checks passed."
  exit 0
else
  echo "Design rule checks FAILED. Fix the items listed above."
  exit 1
fi
