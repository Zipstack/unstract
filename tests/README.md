# Unstract test rig

This directory hosts the test foundation for the Unstract platform: cross-service integration + end-to-end tests, plus the rig that orchestrates every test
suite in the repo (including the per-service unit tests that live alongside their source code).

> Per-service **unit tests stay co-located** with the code they exercise (`backend/<app>/tests/`, `workers/tests/`, `unstract/sdk1/tests/`, etc.).
> Only **e2e** and **cross-service integration** tests live here.

---

## Layout

```
tests/
├── groups.yaml              # SINGLE source of truth: groups, paths, deps
├── critical_paths.yaml      # Critical user/system flows + their declared coverage
├── conftest.py              # Shared pytest markers for the tests/ tree
├── rig/                     # The rig itself (Python package)
│   ├── cli.py               # `python -m tests.rig <subcommand>`
│   ├── groups.py            # YAML loader + dep-graph expansion
│   ├── selection.py         # CLI / file / `all` / changed-only resolution
│   ├── runtime.py           # docker-compose | testcontainers | local
│   ├── reporting.py         # JUnit + markdown summary writer
│   ├── coverage.py          # Per-group coverage files + combine
│   └── critical_paths.py    # Gap + regression detection
├── e2e/
│   ├── conftest.py          # Session-scoped `platform` fixture
│   ├── smoke/               # Login → /health smoke
│   ├── workflows/           # (future) workflow execution e2e
│   ├── api_deployment/      # (future) API deployment e2e
│   ├── prompt_studio/       # (future) Prompt Studio e2e
│   └── hurl/                # (future) hurl-based HTTP suites
├── integration/             # Cross-service tests needing infra but not full platform
├── fixtures/                # Sample PDFs, JSON, adapter configs
└── compose/
    └── docker-compose.test.yaml   # Test overlay on docker/docker-compose.yaml
```

---

## Quick start

```bash
# List every defined group with its tier + dep edges.
tox -e rig -- list-groups

# Show what would actually run for a selection, expanded over depends_on.
tox -e rig -- expand e2e-workflow

# Run all unit groups in parallel, with coverage.
tox -e unit

# Run a single group (positional arg).
tox -e groups -- unit-sdk1

# Run multiple groups; deps are pulled in automatically.
tox -e groups -- unit-backend e2e-smoke

# Run everything (unit + integration + e2e).
tox -e groups -- all

# Pre-commit / fast iteration: read a newline-delimited list of group names.
echo unit-backend > .test-selection
tox -e groups -- --from-file .test-selection --no-coverage --no-parallel

# E2E lane (docker-compose by default; testcontainers for local dev).
tox -e e2e -- e2e-smoke
UNSTRACT_E2E_RUNTIME=testcontainers tox -e e2e -- e2e-smoke
```

The rig CLI is also callable directly without tox:

```bash
python -m tests.rig run --tier unit
python -m tests.rig validate
python -m tests.rig platform up --runtime compose
python -m tests.rig report combine
```

---

## The two manifests

### `groups.yaml` — the unit of selection

Every test group is declared here. The rig refuses to start if `groups.yaml` has a cycle, an unknown `depends_on` target, or a missing path on a
non-`optional` group.

Minimum a new group needs:

```yaml
my-new-group:
  tier: unit            # unit | integration | e2e
  workdir: backend       # where pytest is invoked from
  paths: [some_app/tests] # passed as pytest args
```

Optional knobs (see `groups.yaml` for examples):

| Key | Purpose |
|---|---|
| `markers` | Forwarded to pytest `-m` (e.g. `"unit and not slow"`). |
| `pytest_extra` | Extra pytest CLI flags. |
| `env` | Env vars set for this group's pytest process. |
| `uv_sync_group` | Runs `uv sync --group <name>` in the workdir before pytest. |
| `install_editable` | Runs `uv pip install -e .` in the workdir. |
| `pip_install` | Explicit deps to install before pytest. |
| `requires_services` | Infra needed (`postgres`, `redis`, `minio`, ...). |
| `requires_platform` | Set true for e2e — rig brings the full platform up. |
| `depends_on` | Other groups that must run first. |
| `critical` | Marks the group as covering a critical path. |
| `timeout_seconds` | Override the default 600s. |
| `optional` | Skip silently if paths are missing (use for placeholders). |

### `critical_paths.yaml` — what we promise not to break

Each entry is a high-value user or system flow with an `id`, an `entry` (HTTP endpoint or internal hop), and a list of `covered_by` groups. The rig reports each path as:

- ✅ **covered** — at least one group in `covered_by` ran green this build.
- ⚠️ **gap** — no covering group ran green (or `covered_by` is empty).
- ❌ **regression** — was ✅ on the cached main baseline but isn't now.

The rig itself does not know about PRs or main — it just emits the markers and respects `--fail-on-critical-gap`. The CI workflow at `.github/workflows/ci-test.yaml` is what decides to pass that flag on main and not on PRs, so gaps surface as warnings during review and as errors only when merging. Regressions are **always** errors — the team target is zero.

---

## How selection works

Resolution order, then dep-expansion, then topo-sort:

```
positional GROUPS  ∪  --from-file lines  ∪  --tier filter  ∪  --changed-only diff
```

The literal `all` expands to every group. An empty resolved set is treated as an error, not "run everything" — fail loudly rather than surprise.

`--changed-only` runs `git diff <base>...HEAD` (default base: `origin/main`) and selects every group whose `workdir` or `paths` overlap a changed file.
Useful for fast feedback on feature branches.

---

## E2E runtime

Three modes behind one protocol, chosen by `--runtime` or `UNSTRACT_E2E_RUNTIME`. CI defaults to `compose`; everywhere else defaults to `testcontainers`.

| Mode | Use when | How it works |
|---|---|---|
| `compose` | CI; testing the prod image. | `docker compose -f docker/docker-compose.yaml -f tests/compose/docker-compose.test.yaml up -d --wait`, then HTTP. Teardown wipes volumes. |
| `testcontainers` | Local iteration on infra-only groups. | Stands up Postgres/Redis/RabbitMQ/MinIO via testcontainers and exposes their handles on `PlatformEndpoints.infra`. **Stub today**: does NOT auto-launch backend/prompt-service/etc. as subprocesses — full-platform e2e on testcontainers will need that wiring added. Use `compose` for now if you need the whole stack. |
| `local` | After `./run-platform.sh`. | Assume a developer-managed stack; read URLs from env. |

The rig brings the platform up **once** per `run` invocation (if any selected group has `requires_platform: true`) and exports its URLs via env vars (`UNSTRACT_BACKEND_URL`, `UNSTRACT_PROMPT_SERVICE_URL`, etc.). The rig uses `env.setdefault(...)` so a pre-set value (e.g. from `local` runtime or a developer override) wins over the runtime's default — useful when iterating against a custom stack, but means stale shell env can mask wiring bugs. The smoke test asserts the fixture's URL matches the env var to catch this.

The `platform` pytest fixture in `tests/e2e/conftest.py` reads those env vars; e2e tests run elsewhere (without the rig) just skip with a clear message.

---

## Reports

After every `run`, the rig writes:

```
reports/
├── summary.md                    # human-readable, used for PR sticky comments
├── summary.json                  # machine-readable
├── combined-test-report.md       # alias kept for backward compatibility
├── coverage.xml                  # Cobertura (when --coverage)
├── htmlcov/                      # browsable coverage (when --coverage)
└── <group-name>/
    ├── junit.xml                 # pytest --junitxml
    ├── report.md                 # pytest-md-report output
    └── exit.txt                  # group's pytest exit code
```

`reports/summary.md` has two sections:

1. **Per-group results** table (passed/failed/errors/skipped/duration).
2. **Critical paths**, split into:
   - ❌ Regressions — must be zero.
   - ⚠️ Critical paths not yet covered — the gaps backlog.
   - ✅ Covered critical paths (collapsed) — what's protected.

CI uploads the whole `reports/` directory as an artifact and posts `combined-test-report.md` as a sticky PR comment.

---

## Coverage

Coverage is **on by default** and can be disabled per-run with `--no-coverage` (pre-commit and quick local runs typically disable it).

Each group gets its own `COVERAGE_FILE` so parallel pytest invocations don't trample each other. After all groups complete, the rig runs
`coverage combine` + `coverage xml` + `coverage html`.

We **do not** chase 100% coverage. The bar is critical-path coverage; the rig's job is to make gaps and regressions visible, not to enforce a number.

---

## Branch policy

The rig itself has **no branch awareness**. Branch behavior is enforced in GitHub Actions, not in the rig:

- On `main`, each tier runs in its own step (`tox -e unit` then `tox -e integration`, then `tox -e e2e` in the slow lane). Each invocation passes `--fail-on-critical-gap --update-baseline`. The rig merges (rather than overwrites) covered paths into `previous-summary.json` so the second tier's run preserves the first tier's coverage.
- On PRs, the same tiered steps run without `--fail-on-critical-gap`, so gaps are visible but don't block.
- The e2e workflow only runs on main, on PRs labeled `run-e2e`, on nightly cron, or via manual dispatch.

Developers can scope local runs however they like via positional args, `--from-file .test-selection`, `--tier`, or `--changed-only`.

---

## Adding tests

| Where it goes | What kind of test |
|---|---|
| `backend/<app>/tests/`, `workers/tests/`, `unstract/<lib>/tests/`, ... | Unit tests for that service. |
| `tests/integration/<area>/` | Cross-service tests that need real infra but not the full platform. |
| `tests/e2e/<flow>/` | HTTP-level tests against a running platform. |
| `tests/e2e/hurl/` | Hurl-based HTTP suites. |

After adding tests, either:
1. Reuse an existing group whose `paths` already cover your file, **or**
2. Add a new group to `groups.yaml` (and, if relevant, a `critical_paths.yaml` entry that lists it in `covered_by`).

Validate with `python -m tests.rig validate` before pushing.

---

## Common commands cheat sheet

```bash
# Discovery
python -m tests.rig list-groups
python -m tests.rig list-critical-paths
python -m tests.rig expand e2e-workflow
python -m tests.rig validate

# Running
tox -e unit                                        # all unit groups
tox -e e2e -- e2e-smoke                            # one e2e group
tox -e groups -- unit-backend unit-workers         # multiple groups
tox -e groups -- --from-file .test-selection       # opt-in file
tox -e groups -- --changed-only                    # diff vs origin/main
tox -e groups -- all --no-coverage                 # everything, fast

# Platform control (manual)
python -m tests.rig platform up --runtime compose
python -m tests.rig platform down

# Re-aggregate existing reports
python -m tests.rig report combine
```
