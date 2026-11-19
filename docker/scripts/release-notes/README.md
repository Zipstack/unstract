# Print Release Notes

## When an entry is owed

`run-platform.sh --update` prints this file, so it is the **only in-repo channel
that reaches a self-hosted compose operator at upgrade time**. An entry is owed
whenever taking a release requires the operator to *do* something, or changes
something they have already configured — a data migration, a renamed or removed
env var, a moved URL, a changed default they may have pinned.

Two things make this easy to miss:

- **The audience is wider than "OSS-only".** `copy_cloud_deps.py` copies cloud
  plugins — including the Agent-KV capability marker — into an OSS checkout,
  which is the tree that holds `run-platform.sh` and this file. Such a stack
  reads these notes *and* runs the enterprise features, so "this only affects
  OSS, which cannot use the feature" is not a reason to skip an entry.
- **`.env` values survive upgrades.** `merge_env.py` keeps the existing value
  for any key outside `PREFERRED_BASE_ENV_KEYS`, and re-appends it under
  `# Additional envs` even if the sample drops the line. So changing a default
  in `sample.env` does **not** change what an upgraded deployment serves —
  only an entry here tells the operator to edit it.

## Getting the key right

Keys are semver (`vX.Y.Z`) and a note fires only when
`current < key <= target` (`print_release_notes.py`), so the key must be the
release that **actually carries** the change. Both ways of being wrong cost
something, and they are not symmetric:

- **Key too high** — operators who upgrade past the real change but stop below
  the key are broken with no warning.
- **Key too low** — the note fires for people whose build does not have the
  change yet, *and* anyone who stops on a version at or above the key never sees
  it afterwards (`v0.205.0 -> v0.206.0` shows nothing for a `v0.205.0` key).

So prefer an entry whose ACTION is safe on both sides of its own boundary —
"remove this override" is, "set it to this new value" is not — and confirm the
key at cut.

**To find the next version without creating anything:** run the *Create Release*
workflow with `dry_run: true`, which computes and prints it. Or reproduce its
`auto` rule locally — minor if any `[FEAT]`/`[GATED-FEAT]` PR merged since the
last release, else patch:

```shell
LATEST=$(gh api repos/Zipstack/unstract/releases \
  --jq '[.[] | select(.tag_name | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$"))][0].tag_name')
SINCE=$(gh api "repos/Zipstack/unstract/releases/tags/$LATEST" --jq .published_at)
gh pr list --repo Zipstack/unstract --base main --state merged --limit 200 \
  --search "merged:>$SINCE" --json title \
  | jq '[.[] | select(.title | test("\\[(FEAT|GATED-FEAT)\\]"; "i"))] | length'
```

Note the community `vX.Y.Z` series is **not** the enterprise `ee-vX.Y.Z` line —
different numbering, and this file is keyed by the community one.

**Open at the time of writing:** the `v0.205.0` entry (the Agent-KV public path
rename, UN-4044) was keyed from that computation while the change was still an
open PR. **Whoever cuts the release should confirm the rename is in it** and
move the key if it landed later; `docs/agent-kv-api.md` §11 item 12 is the full
description.

Accepts `current_version` and `target_version` as inputs to print the necessary release notes / warnings to be shown while updating a release

Run below to get more information on the usage

```shell
python print_release_notes.py -h
```

Make sure to create / activate a virtual environment with the below commands

```shell
uv venv
source .venv/bin/activate
```
