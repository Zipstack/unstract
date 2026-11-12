#!/bin/sh
# Runs a guard ("$@") the way CI does: inside a real git repository whose root
# is one level above frontend/, so paths, --relative, renames, quoting and
# .gitignore all behave as on a PR. Used by boundary.fixtures.mjs.
#
# The case's tree (the current directory) is committed as the base, on
# branch `base`. Then the case's change.sh, if any, runs in frontend/ and its
# result is committed on top. change.sh itself is part of the base commit, so
# it is never part of the change.
set -eu
here=$(pwd)
repo=$(mktemp -d)
trap 'rm -rf "$repo"' EXIT
mkdir "$repo/frontend"
for entry in "$here"/* "$here"/.gitignore; do
  [ "$(basename "$entry")" = node_modules ] || cp -R "$entry" "$repo/frontend/"
done
ln -s "$here/node_modules" "$repo/frontend/node_modules"
# The repository's own rule for the cloud overlay (D7).
printf '%s\n' 'frontend/src/v1/plugins/*' '!frontend/src/v1/plugins/manifest.ts' \
  >"$repo/.gitignore"
cd "$repo"
git init -q
git config user.email fixtures@example.com
git config user.name fixtures
git config core.quotePath true
git add -A
git commit -q -m base
git branch base
if [ -f frontend/change.sh ]; then
  (cd frontend && sh change.sh)
fi
git add -A
git commit -q --allow-empty -m change
cd frontend
"$@"
