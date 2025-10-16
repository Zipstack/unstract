#!/bin/bash
set -euo pipefail

# Script to combine multiple test reports into a single markdown file
# Usage: ./combine-test-reports.sh

OUTPUT_FILE="combined-test-report.md"
REPORTS=()

# Find all test report files
for report in runner-report.md sdk1-report.md; do
    if [ -f "$report" ]; then
        REPORTS+=("$report")
    fi
done

# Exit if no reports found
if [ ${#REPORTS[@]} -eq 0 ]; then
    echo "No test reports found. Skipping report generation."
    exit 0
fi

# Function to extract test counts from a report
extract_test_counts() {
    local report_file=$1
    local passed=0
    local failed=0
    local total=0

    # Try to find "Passed:" or "passed:" patterns (handles markdown formatting)
    if grep -qiE '(passed|✅.*passed)' "$report_file"; then
        passed=$(grep -iE '(passed|✅.*passed)' "$report_file" | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # Try to find "Failed:" or "failed:" patterns (handles markdown formatting)
    if grep -qiE '(failed|❌.*failed)' "$report_file"; then
        failed=$(grep -iE '(failed|❌.*failed)' "$report_file" | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # Try to find "Total" patterns (handles markdown formatting with ** and -)
    if grep -qiE '(total.*tests?|tests?.*total)' "$report_file"; then
        total=$(grep -iE '(total.*tests?|tests?.*total)' "$report_file" | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # If total not found, calculate from passed + failed
    if [ "$total" -eq 0 ]; then
        total=$((passed + failed))
    fi

    echo "${total}:${passed}:${failed}"
}

# Initialize the combined report with collapsed summary
cat > "$OUTPUT_FILE" << 'EOF'
# Test Results

<details open>
<summary><b>Summary</b></summary>

EOF

# Extract and display summary for each report
for report in "${REPORTS[@]}"; do
    report_name=$(basename "$report" .md)

    # Convert report name to title case
    if [ "$report_name" = "runner-report" ]; then
        title="Runner Tests"
    elif [ "$report_name" = "sdk1-report" ]; then
        title="SDK1 Tests"
    else
        title="${report_name}"
    fi

    # Extract counts
    counts=$(extract_test_counts "$report")
    IFS=':' read -r total passed failed <<< "$counts"

    # Determine status icon
    if [ "$failed" -gt 0 ]; then
        status="❌"
    elif [ "$passed" -gt 0 ]; then
        status="✅"
    else
        status="⚠️"
    fi

    echo "- ${status} **${title}**: ${passed} passed, ${failed} failed (${total} total)" >> "$OUTPUT_FILE"
done

cat >> "$OUTPUT_FILE" << 'EOF'

</details>

---

EOF

# Combine all reports with collapsible sections
for report in "${REPORTS[@]}"; do
    report_name=$(basename "$report" .md)

    # Convert report name to title case
    if [ "$report_name" = "runner-report" ]; then
        title="Runner Tests"
    elif [ "$report_name" = "sdk1-report" ]; then
        title="SDK1 Tests"
    else
        title="${report_name}"
    fi

    echo "<details>" >> "$OUTPUT_FILE"
    echo "<summary><b>${title} - Full Report</b></summary>" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    cat "$report" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
    echo "</details>" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
done

echo "Combined test report created: $OUTPUT_FILE"
echo "Included reports: ${REPORTS[*]}"
