/*
 * Proves the v1 test harness fails a test when it should. Run by
 * `bun run test:v1` with `node --test`: each case is a real vitest run of the
 * v1 config (via ./vitest.config.mts) over one file in ./cases, which live
 * outside src/ so the v1 suite, lint and typecheck never pick them up.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { test } from "node:test";

const FRONTEND = path.resolve(import.meta.dirname, "..", "..");
const CONFIG = path.join("test-fixtures", "v1-harness", "vitest.config.mts");

function runCase(file) {
  const result = spawnSync(
    "npx",
    [
      "--no-install",
      "vitest",
      "run",
      "--config",
      CONFIG,
      path.join("test-fixtures", "v1-harness", "cases", file),
    ],
    { cwd: FRONTEND, encoding: "utf8", env: { ...process.env, CI: "1" } },
  );
  return { status: result.status, output: `${result.stdout}${result.stderr}` };
}

const CASES = [
  {
    file: "unmocked-fetch.test.tsx",
    fails: true,
    names: "GET http://localhost:3000/api/v1/unstract/org-1/adapter/?type=LLM",
  },
  {
    file: "unmocked-xhr.test.ts",
    fails: true,
    names: "POST http://localhost:3000/api/v1/unstract/org-1/workflow/",
  },
  { file: "mocked-fetch.test.ts", fails: false },
];

for (const { file, fails, names } of CASES) {
  test(`${file} ${fails ? "fails, naming the request" : "passes"}`, () => {
    const { status, output } = runCase(file);
    if (fails) {
      assert.notEqual(status, 0, output);
      assert.match(output, /Unmocked request \(add a handler/);
      assert.ok(output.includes(names), output);
      // Answered by the harness, never sent: no connection was attempted.
      assert.doesNotMatch(output, /ECONNREFUSED/);
    } else {
      assert.equal(status, 0, output);
    }
  });
}
