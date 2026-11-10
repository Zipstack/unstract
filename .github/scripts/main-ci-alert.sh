#!/usr/bin/env bash
# Slack alert for a workflow that failed on a push to main; see
# .github/workflows/main-ci-alert.yaml. Names the author of every PR merged
# since that workflow's last green run on main, since any of them may have
# caused the failure. If main was already failing, only the PRs since that
# failing run are named, whether or not an alert for that run named the earlier
# ones. Bot PRs and pushes that came from no PR are left out.
# The PR list is best-effort: if it cannot be built, the alert still posts.
# DRY_RUN=1 prints the payload instead of posting it.
set -euo pipefail

: "${REPO:?}" "${SERVER_URL:?}" "${WORKFLOW_ID:?}" "${WORKFLOW_NAME:?}"
: "${RUN_URL:?}" "${RUN_CREATED:?}" "${HEAD_SHA:?}" "${ALERT_RUN_URL:?}"

MAX_LINES=${MAX_LINES:-50}
# Stop looking up PRs after this many seconds. With one more 20s lookup and
# curl's 60s retry cap plus one 30s attempt, the post fits in the job's 5 minutes.
BUDGET=${BUDGET:-150}

gh_api() { timeout 20 gh api "$@"; }

# Prints the PR list. The runs and compare calls carry `|| return`, because
# set -e is ignored inside a function that is called from an `if !` condition.
# A failed PR lookup only replaces that commit's line.
list_prs() {
  local prev base conclusion shas sha line found=0 checked=0 fetched total
  # The newest run before this one that passed or failed. Cancelled and
  # skipped runs decide nothing. The strict created filter leaves out this run,
  # which has already completed, and any later push's run, which a re-run of
  # this run may also find completed.
  prev=$(gh_api -X GET "repos/$REPO/actions/workflows/$WORKFLOW_ID/runs" \
    -f branch=main -f event=push -f status=completed -f "created=<$RUN_CREATED" -f per_page=100 \
    --jq '[.workflow_runs[] | select(.conclusion | IN("success", "failure", "startup_failure", "timed_out"))]
      | first // empty | "\(.head_sha) \(.conclusion)"') || return
  if [ -n "$prev" ]; then
    base=${prev% *}
    conclusion=${prev#* }
    if [ "$conclusion" = success ]; then
      echo "PRs merged since the last green run:"
    else
      echo "\`main\` was already failing at ${base:0:7}. PRs merged since then:"
    fi
    # Compare returns at most 250 commits: the newest, oldest first.
    shas=$(gh_api "repos/$REPO/compare/$base...$HEAD_SHA" \
      --jq '"\(.total_commits) \([.commits[].sha] | reverse | join(" "))"') || return
    total=${shas%% *}
    shas=${shas#* }
  else
    echo "No earlier passed or failed run on \`main\`, so only the head commit is checked:"
    total=1
    shas=$HEAD_SHA
  fi
  fetched=$(wc -w <<<"$shas")

  for sha in $shas; do
    if [ "$found" -ge "$MAX_LINES" ] || [ "$SECONDS" -ge "$BUDGET" ]; then
      break
    fi
    checked=$((checked + 1))
    # Pushes made without a PR drop out here.
    if ! line=$(gh_api "repos/$REPO/commits/$sha/pulls" | jq -r --arg url "$SERVER_URL/$REPO" '
      def esc: gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;");
      map(select(.user.type != "Bot")) | first // empty
      | "• <\($url)/pull/\(.number)|#\(.number)> \(.title | esc) by @\(.user.login)"'); then
      line="• ${sha:0:7}: could not look up its PR"
    fi
    if [ -n "$line" ]; then
      echo "$line"
      found=$((found + 1))
    fi
  done

  if [ "$found" -eq 0 ] && [ "$checked" -eq "$fetched" ]; then
    echo "no human-authored PRs"
  fi
  if [ "$checked" -lt "$fetched" ]; then
    echo "…$((fetched - checked)) older commits not checked"
  fi
  if [ "$fetched" -lt "$total" ]; then
    echo "…$((total - fetched)) older commits not listed: compare returns at most 250"
  fi
}

if ! body=$(list_prs); then
  echo "::warning::Could not list the PRs behind this failure"
  body="Could not list the PRs behind this failure; see <${ALERT_RUN_URL}|the alert job's log>."
fi

text=":red_circle: *${WORKFLOW_NAME}* failed on \`main\`: <${RUN_URL}|view run>
${body}"

payload=$(jq -n --arg text "$text" '{text: $text}')
if [ "${DRY_RUN:-}" = 1 ]; then
  echo "$payload"
else
  : "${SLACK_WEBHOOK_URL:?}"
  curl -fsS --max-time 30 --retry 3 --retry-max-time 60 -X POST -H 'Content-Type: application/json' \
    --data "$payload" "$SLACK_WEBHOOK_URL"
fi
