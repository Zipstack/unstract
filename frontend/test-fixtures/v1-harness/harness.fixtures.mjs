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
// The lockfile's vitest, run by this same node: nothing resolved from PATH.
const VITEST = path.join(FRONTEND, "node_modules", "vitest", "vitest.mjs");

function runCase(file) {
  const result = spawnSync(
    process.execPath,
    [
      VITEST,
      "run",
      "--config",
      CONFIG,
      path.join("test-fixtures", "v1-harness", "cases", file),
    ],
    { cwd: FRONTEND, encoding: "utf8", env: { ...process.env, CI: "1" } },
  );
  // Colour codes would split the reporter's lines the assertions match on.
  const output = `${result.stdout}${result.stderr}`.replace(
    // biome-ignore lint/suspicious/noControlCharactersInRegex: ANSI escapes
    /\u001b\[[0-9;]*m/g,
    "",
  );
  return { status: result.status, output };
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
  {
    file: "unmocked-websocket.test.ts",
    fails: true,
    names: "WEBSOCKET ws://localhost:3000/api/v1/socket",
  },
  {
    // The request starts in cleanup(), after the test body, in the last test.
    file: "unmocked-on-unmount.test.tsx",
    fails: true,
    names: "POST http://localhost:3000/api/v1/unstract/org-1/draft/",
  },
  {
    // ...and fails the test that unmounted, not the one after it.
    file: "unmocked-on-unmount-attribution.test.tsx",
    fails: true,
    names: "GET http://localhost:3000/api/v1/unstract/org-1/unmount/",
    summary: /Tests\s+1 failed \| 1 passed/,
    failed: "first: requests on unmount",
  },
  {
    // Fired by a timer after the last test's afterEach.
    file: "unmocked-after-last-test.test.ts",
    fails: true,
    names: "GET http://localhost:3000/api/v1/unstract/org-1/poll/",
  },
  {
    // resetHandlers(...handlers) must keep the catch-all.
    file: "reset-handlers-with-args.test.ts",
    fails: true,
    names: "GET http://localhost:3000/api/v1/unstract/org-1/unknown/",
  },
  { file: "mocked-fetch.test.ts", fails: false },
  // A test that leaves fake timers on must not hang the next one's teardown.
  { file: "fake-timers-left-on.test.ts", fails: false },
];

for (const { file, fails, names, summary, failed } of CASES) {
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
    if (summary) {
      assert.match(output, summary);
    }
    if (failed) {
      assert.match(output, new RegExp(`FAIL .*> ${failed}`));
    }
  });
}
