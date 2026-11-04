/*
 * Proves the `v1 · Unit tests` check (ci-frontend-v1.yaml) gates what it
 * should: it runs the rig's `frontend-v1-unit` group config, and that config
 * fails a run below v1's coverage threshold even when every test passes.
 * Run by `bun run test:v1` and the `v1 · Guard fixtures` check.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";

const FRONTEND = path.resolve(import.meta.dirname, "..", "..");
const REPO = path.resolve(FRONTEND, "..");
const CONFIG = path.join("test-fixtures", "v1-unit-gate", "vitest.config.mts");
// The lockfile's vitest, run by this same node: nothing resolved from PATH.
const VITEST = path.join(FRONTEND, "node_modules", "vitest", "vitest.mjs");

function runCase(name) {
  const reports = mkdtempSync(path.join(tmpdir(), "v1-unit-gate-"));
  try {
    const result = spawnSync(
      process.execPath,
      [VITEST, "run", "--config", CONFIG],
      {
        cwd: FRONTEND,
        encoding: "utf8",
        env: {
          ...process.env,
          CI: "1",
          V1_GATE_CASE: name,
          V1_GATE_REPORTS: reports,
        },
      },
    );
    const output = `${result.stdout}${result.stderr}`.replace(
      // biome-ignore lint/suspicious/noControlCharactersInRegex: ANSI escapes
      /\u001b\[[0-9;]*m/g,
      "",
    );
    return { status: result.status, output };
  } finally {
    rmSync(reports, { recursive: true, force: true });
  }
}

test("passing tests below the coverage threshold fail the gate", () => {
  const { status, output } = runCase("below-threshold");
  assert.notEqual(status, 0, output);
  assert.match(output, /Tests\s+1 passed/);
  assert.match(
    output,
    /Coverage for lines \([\d.]+%\) does not meet global threshold \(80%\)/,
  );
});

test("passing tests at the coverage threshold pass the gate", () => {
  const { status, output } = runCase("at-threshold");
  assert.equal(status, 0, output);
});

// The `frontend-v1-unit` block of tests/groups.yaml, up to the next group.
function groupBlock(yaml, name) {
  const start = yaml.indexOf(`\n  ${name}:\n`);
  assert.notEqual(start, -1, `tests/groups.yaml has no ${name} group`);
  const rest = yaml.slice(start + name.length + 5);
  const end = rest.search(/\n {2}[a-z0-9-]+:\n/);
  return end === -1 ? rest : rest.slice(0, end);
}

test("the CI unit check runs the rig group's vitest config", () => {
  const groups = readFileSync(path.join(REPO, "tests", "groups.yaml"), "utf8");
  const config = groupBlock(groups, "frontend-v1-unit").match(
    /^\s+vitest_config:\s*(\S+)\s*$/m,
  )?.[1];
  assert.ok(config, "frontend-v1-unit sets no vitest_config");

  const workflow = readFileSync(
    path.join(REPO, ".github", "workflows", "ci-frontend-v1.yaml"),
    "utf8",
  );
  const job = workflow.slice(workflow.indexOf("\n  unit:\n"));
  assert.ok(job.length > 1, "ci-frontend-v1.yaml has no `unit` job");
  const run = job.match(/^\s+run: (.*vitest run.*)$/m)?.[1];
  assert.ok(run, "the `unit` job runs no vitest");
  assert.ok(
    run.includes(`--config ${config}`),
    `the \`unit\` job runs \`${run}\`, not the group's config ${config}`,
  );
});
