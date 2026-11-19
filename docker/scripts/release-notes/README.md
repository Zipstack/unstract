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

Keys are semver (`vX.Y.Z`) and a note fires when
`current < key <= target` (`print_release_notes.py`), so the key must be the
release that actually carries the change. That is why an entry usually cannot be
written in the PR that makes the change — the version is not known yet — and has
to be added at release cut instead. **Owed at the next cut:** the Agent-KV
public path rename (UN-4044), `docs/agent-kv-api.md` §11 item 12.

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
