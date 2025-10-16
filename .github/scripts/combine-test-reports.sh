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

# Function to extract test counts from pytest-md-report markdown table
extract_test_counts() {
    local report_file=$1
    local passed=0
    local failed=0
    local total=0

    # Find the header row to determine column positions
    local header_line=$(grep -E '^\|\s*(filepath|file)' "$report_file" | head -1)

    if [ -z "$header_line" ]; then
        echo "0:0:0"
        return
    fi

    # Extract column names and find positions
    IFS='|' read -ra headers <<< "$header_line"
    local passed_col=-1
    local failed_col=-1
    local subtotal_col=-1

    for i in "${!headers[@]}"; do
        local col=$(echo "${headers[$i]}" | tr -d ' ' | tr '[:upper:]' '[:lower:]')
        case "$col" in
            passed) passed_col=$i ;;
            failed) failed_col=$i ;;
            subtotal|sub) subtotal_col=$i ;;
        esac
    done

    # Find the TOTAL row (handles both "TOTAL" and "**TOTAL**" bold markdown)
    local total_line=$(grep -E '^\|\s*\*?\*?TOTAL' "$report_file" | head -1)

    if [ -z "$total_line" ]; then
        echo "0:0:0"
        return
    fi

    # Parse the TOTAL row values
    IFS='|' read -ra values <<< "$total_line"

    # Extract passed count
    if [ "$passed_col" -ge 0 ] && [ "$passed_col" -lt "${#values[@]}" ]; then
        passed=$(echo "${values[$passed_col]}" | tr -d ' ' | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # Extract failed count
    if [ "$failed_col" -ge 0 ] && [ "$failed_col" -lt "${#values[@]}" ]; then
        failed=$(echo "${values[$failed_col]}" | tr -d ' ' | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # Extract total from SUBTOTAL column, or calculate it
    if [ "$subtotal_col" -ge 0 ] && [ "$subtotal_col" -lt "${#values[@]}" ]; then
        total=$(echo "${values[$subtotal_col]}" | tr -d ' ' | grep -oE '[0-9]+' | head -1 || echo "0")
    fi

    # If total is still 0, calculate from passed + failed
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
