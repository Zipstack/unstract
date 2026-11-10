#!/usr/bin/env bash
# Slack alert for a workflow that failed on a push to main; see
# .github/workflows/main-ci-alert.yaml. Lists every PR merged since that
# workflow's last green run on main, so all PRs that could have caused the
# failure are named. Bot PRs and non-PR pushes are left out. DRY_RUN=1 prints
# the payload instead of posting it.
set -euo pipefail

: "${REPO:?}" "${SERVER_URL:?}" "${WORKFLOW_ID:?}" "${WORKFLOW_NAME:?}"
: "${RUN_URL:?}" "${RUN_CREATED:?}" "${HEAD_SHA:?}"

MAX_LINES=50

# A success created after this run (a later push, or a re-run) is not a
# baseline for it, hence the created filter.
base=$(gh api -X GET "repos/$REPO/actions/workflows/$WORKFLOW_ID/runs" \
  -f branch=main -f event=push -f status=success -f "created=<$RUN_CREATED" -f per_page=1 \
  --jq '.workflow_runs[0].head_sha // empty')

commits='[]'
if [ -n "$base" ]; then
  # Compare returns oldest first and at most 250 commits.
  commits=$(gh api "repos/$REPO/compare/$base...$HEAD_SHA" --jq '.commits')
fi
if [ "$commits" = '[]' ]; then
  # No green run to compare against: fall back to the head commit.
  commits=$(gh api "repos/$REPO/commits/$HEAD_SHA" --jq '[.]')
fi

lines=$(jq -r --arg url "$SERVER_URL/$REPO" --argjson max "$MAX_LINES" '
  def esc: gsub("&"; "&amp;") | gsub("<"; "&lt;") | gsub(">"; "&gt;");
  def title: .commit.message | split("\n")[0];
  def bot: (.author.type // "") == "Bot"
    or ((.author.login // .commit.author.name // "") | endswith("[bot]"));
  # Squash merges end in "(#N)"; anything else (release and Helm-bump pushes) is not a PR.
  [ .[] | select((title | test("\\(#[0-9]+\\)$")) and (bot | not)) ] | reverse
  | (.[:$max][] | "• <\($url)/commit/\(.sha)|\(.sha[0:7])> \(title | esc) by "
      + (if .author.login then "@\(.author.login)" else (.commit.author.name | esc) end)),
    (if length > $max then "…and \(length - $max) more" else empty end)
' <<<"$commits")

text=":red_circle: *${WORKFLOW_NAME}* failed on \`main\`: <${RUN_URL}|view run>
PRs merged since the last green run:
${lines:-no human-authored PRs}"

payload=$(jq -n --arg text "$text" '{text: $text}')
if [ "${DRY_RUN:-}" = 1 ]; then
  echo "$payload"
else
  : "${SLACK_WEBHOOK_URL:?}"
  curl -fsS -X POST -H 'Content-Type: application/json' --data "$payload" "$SLACK_WEBHOOK_URL"
fi
