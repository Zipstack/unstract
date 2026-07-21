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
│   ├── conftest.py          # `platform` fixture + `provisioned_workflow` chain
│   ├── smoke/               # Login → /health smoke
│   ├── workflows/           # Workflow execution e2e (mocked LLM)
│   ├── api_deployment/      # API deployment e2e: run, callback delivery, fan-out (all async)
│   ├── etl/                 # ETL pipeline e2e (MinIO source + destination)
│   ├── prompt_studio/       # Prompt Studio fetch-response e2e
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
| `optional` | Two effects: (1) skip silently if paths/workdir are missing (placeholders, gitignored cloud-only dirs); (2) **non-blocking** — if the group runs and fails, its red result still shows in the summary but does not gate the overall exit code. Use for groups that need infra CI doesn't provision (e.g. live-DB connector tests) where a red run shouldn't block merge. |

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

### Hermetic LLM (`UNSTRACT_LLM_MOCK_RESPONSE`)

Execute-path e2e tests must not call a real provider, so the rig sets `UNSTRACT_LLM_MOCK_RESPONSE` (default `MOCK_LLM_OK`) before boot, for any runtime and treating an exported empty string as unset. The test overlay forwards it into the workers, and `unstract.sdk1.llm` passes it to litellm as `mock_response`: for the non-streaming completion path litellm returns the string verbatim with fixed usage (10 prompt / 20 completion / 30 total), so both the answer and the token counts are exact-assertable. Streaming (`stream_complete`) goes through a different litellm path whose usage differs, so don't assume 10/20/30 there. Sentinels like `litellm.RateLimitError` force error paths. Unset (the production default) the hook is a no-op.

Mocking needs two conditions, not one: `ENVIRONMENT` must also be `test` or `development`. Production sets neither variable, so a stray mock var alone cannot fake completions and their billing — and a refusal is logged rather than silent, since setting the var at all means someone expected mocking. `development` is allowed because that is what base compose sets on the workers that run the injection; the test overlay pins `ENVIRONMENT=test` on those same two workers explicitly, so the tier can't lose its mock to a base-compose edit.

A CI/dev override wins (the rig only fills an unset value). Running these tests under the rig **fails** if the var is missing; running **without** the rig just skips the execute-path tests — export it on both sides (your shell and the workers) if you boot the stack yourself.

While the mock is active platform-wide, the LLM adapter's test-connection cannot pass: it regex-matches the completion for a specific city, which `MOCK_LLM_OK` won't satisfy — so `adapter-register-llm` stays an e2e gap for now.

Only `LLM` completions are mocked, not embeddings: `provisioned_workflow` pins `chunk_size=0` so indexing never invokes `litellm.embedding`. A test that needs chunking will need the embedding path mocked too.

### Fan-out (`MAX_PARALLEL_FILE_BATCHES`)

Defaults to `1`, meaning every file of a multi-file run lands in one batch and is processed serially — so a fan-out test would pass without any fan-out happening. The overlay defaults it to `3` on `backend`, which is what normally takes effect: workers ask the backend for this value and fall back to their own env only when they can't reach it or it carries no value (the overlay sets it on `worker-api-deployment-v2` too, to keep the fallback in step). Batches are `min(MAX_PARALLEL_FILE_BATCHES, num_files)`, so N files with the same N gives one batch each.

**The fan-out half is an open gap** (`workflow-execution-fan-out` in `critical_paths.yaml`), and closing it needs a product change, not a cleverer test. Nothing persists a batch or task id: the batch index is a discarded loop local, and the celery task id only ever reaches worker stdout. That leaves per-file timing as the only proxy, and timing does not work here — measured on CI, three files genuinely fanned out finished *further* apart (durations `6.6 / 18.1 / 22.9`) than the ~2s steps seen when they share a batch, because three concurrent tool containers on a loaded runner cost more in contention than they gain in overlap. No threshold separates those two distributions, and no delay value fixes it: the contention scales with the parallelism being measured.

Worth stating plainly because the design is tempting: overlap of the row windows doesn't discriminate either, since a serialised batch pre-creates all its rows in one call and they overlap trivially.

What would close it is a batch or task identifier on `WorkflowFileExecution` — the test then asserts N distinct ids for N files, with no timing and no stall. That is also ordinary execution observability, which is the argument for doing it in the product rather than the test.

`e2e-api-deployment` still asserts the rejoin: one result per file, all files counted into `successful_files`, one row per file.

### ETL (MinIO)

`tests/e2e/etl` runs a pipeline from a source connector to a destination connector. MinIO is the only storage connector the compose stack both boots and registers — the local-filesystem one would need no infra but is never registered (`local_storage/` has no `__init__.py`, so `register_connectors` skips it), which is why the mounted `./workflow_data:/data` volume can't be used as an ETL endpoint. The test seeds and reads its objects over the published port (`UNSTRACT_MINIO_ENDPOINT`, default `localhost:9000`) while the workers reach the same store over the compose network (`UNSTRACT_MINIO_INTERNAL_URL`, default `http://unstract-minio:9000`). It skips when no MinIO answers, so it does not fail a runtime that publishes none.

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

### Backend: no registration needed

1. Write a normal test in `backend/<app>/tests/test_<name>.py`. The filename
   **must** match `test_*.py`, `*_test.py`, `*_tests.py`, or Django's per-app
   `tests.py` — anything else is silently never collected. Prefer `test_*.py`
   for consistency.
2. Tier is inferred, not declared. A test that touches the database (subclasses
   Django `TestCase`/`APITestCase`, or uses `@pytest.mark.django_db`) is
   auto-marked `integration` by `backend/conftest.py` and runs in
   `integration-backend` against a rig-provisioned Postgres/Redis. Everything
   else runs in `unit-backend`. No marker, no `groups.yaml` edit.
3. Don't stub the environment. The rig runs the whole backend tree in one
   pytest session with Django fully loaded — tests that patch `sys.modules`,
   assume import order, or assume they run alone will break under collection.
   Use `unittest.mock.patch` on real modules; mock only true externals
   (LLM SDKs, third-party APIs) — never the ORM or serializers.
4. Seed data per test in `setUp` via the ORM. Schema comes from migrations
   (run once per session); each test's writes roll back automatically.
5. Needs credentials CI doesn't have (external DB/SaaS)? Guard with
   `self.skipTest("<CRED_VAR> not set")` in `setUp` — it skips in CI and runs
   locally when the env vars are exported.

Run it locally:

```bash
tox -e groups -- unit-backend --no-coverage          # pure tests
tox -e groups -- integration-backend --no-coverage   # DB tests (needs Docker)
```

List what a group would run (no DB required):

```bash
cd backend && uv run --group test pytest . -m integration --collect-only -q
```

### Other services / new areas

Outside backend, markers are manual (`workers` enforces `--strict-markers`).
Either reuse an existing group whose `paths` already cover your file, or add a
group to `groups.yaml` (and, if relevant, list it in a `critical_paths.yaml`
entry's `covered_by`). Validate with `python -m tests.rig validate` before
pushing.

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
