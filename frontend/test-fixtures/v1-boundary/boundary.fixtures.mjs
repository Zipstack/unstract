/*
 * Proves the v1 guardrails fail when they should and pass when they should.
 * Run by `bun run test:v1` (with `node --test`, not vitest, so the v0 suite
 * never collects it).
 *
 * Each case builds a throwaway copy of the frontend: biome.json,
 * package.json, scripts/, the real src/v1 scaffold and a node_modules
 * symlink. It then overlays the files under cases/<name>/ and runs the real
 * package.json scripts (or a raw command) inside it. The known-bad files
 * live here, outside src/, so they never reach the real lint or typecheck.
 */
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

const FRONTEND = path.resolve(import.meta.dirname, "..", "..");
const CASES_DIR = path.join(import.meta.dirname, "cases");
const { scripts } = JSON.parse(
  fs.readFileSync(path.join(FRONTEND, "package.json"), "utf8"),
);

/*
 * `run` holds package.json script names, or raw commands for the v0 side,
 * which has no v1 script. `fails` is a substring the output must contain;
 * cases without it must pass.
 */
const CASES = [
  // The empty scaffold passes everything.
  { name: null, run: ["typecheck:v1", "lint:v1"] },

  // Import boundary, v1 -> v0 (Biome).
  {
    name: "v1-imports-v0-alias",
    run: ["lint:v1"],
    fails: "v1 imports nothing outside src/v1",
  },
  {
    name: "v1-imports-v0-relative",
    run: ["lint:v1"],
    fails: "v1 imports nothing outside src/v1",
  },

  // Import boundary, v0 -> v1 (Biome).
  {
    name: "v0-imports-v1-internal",
    run: ["biome lint src/"],
    fails: "v0 may import only the v1 public entry",
  },
  {
    name: "v0-imports-v1-relative",
    run: ["biome lint src/"],
    fails: "v0 may import only the v1 public entry",
  },
  { name: "v0-imports-v1-entry", run: ["biome lint src/"] },

  // Banned under v1.
  { name: "v1-prop-types", run: ["lint:v1"], fails: "PropTypes are not used" },
  {
    name: "v1-prop-types-assignment",
    run: ["lint:v1"],
    fails: "No PropTypes under v1",
  },
  {
    name: "v1-component-css-import",
    run: ["lint:v1"],
    fails: "No component .css under src/v1",
  },
  {
    name: "v1-component-css-file",
    run: ["typecheck:v1"],
    fails: "No component style files",
  },
  {
    name: "v1-ant-class-prefix",
    run: ["lint:v1"],
    fails: "No antd 'ant-' class names",
  },
  { name: "v1-explicit-any", run: ["lint:v1"], fails: "noExplicitAny" },
  // The v1 override must add to the shared rules, not replace them.
  {
    name: "v1-base-rules-still-apply",
    run: ["lint:v1"],
    fails: "noDoubleEquals",
  },

  // TypeScript only, strict.
  { name: "v1-js-file", run: ["typecheck:v1"], fails: "TypeScript only" },
  {
    name: "v1-implicit-any",
    run: ["typecheck:v1"],
    fails: "implicitly has an 'any' type",
  },
  {
    name: "v1-unused-local",
    run: ["typecheck:v1"],
    fails: "is declared but its value is never read",
  },

  // Folder taxonomy and contract.
  {
    name: "v1-outside-taxonomy",
    run: ["typecheck:v1"],
    fails: "Outside the v1 folder taxonomy",
  },
  {
    name: "v1-ui-imports-services",
    run: ["lint:v1"],
    fails: "components/ui/ may not import from services/",
  },
  {
    name: "v1-page-imports-other-page",
    run: ["lint:v1"],
    fails: "pages/projects/ may not import from pages/settings/",
  },
  { name: "v1-allowed-imports", run: ["typecheck:v1", "lint:v1"] },
];

function makeTree(caseName) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v1-boundary-"));
  for (const file of ["biome.json", "package.json", "vite-env.d.ts"]) {
    fs.copyFileSync(path.join(FRONTEND, file), path.join(dir, file));
  }
  // Copied, not linked: check-v1.mjs finds src/v1 relative to itself.
  fs.cpSync(path.join(FRONTEND, "scripts"), path.join(dir, "scripts"), {
    recursive: true,
  });
  fs.cpSync(path.join(FRONTEND, "src", "v1"), path.join(dir, "src", "v1"), {
    recursive: true,
  });
  fs.symlinkSync(
    path.join(FRONTEND, "node_modules"),
    path.join(dir, "node_modules"),
    "dir",
  );
  if (caseName) {
    fs.cpSync(path.join(CASES_DIR, caseName), dir, { recursive: true });
  }
  // biome.json enables VCS integration with `useIgnoreFile`, which needs a
  // repository root holding an ignore file.
  execFileSync("git", ["init", "-q"], { cwd: dir });
  fs.writeFileSync(path.join(dir, ".gitignore"), "node_modules\n");
  return dir;
}

function removeTree(dir) {
  // Unlink first so the recursive delete can never walk into node_modules.
  fs.unlinkSync(path.join(dir, "node_modules"));
  fs.rmSync(dir, { recursive: true, force: true });
}

function runAll(dir, run) {
  let output = "";
  for (const step of run) {
    const command = scripts[step] ?? step;
    const result = spawnSync("sh", ["-c", command], {
      cwd: dir,
      encoding: "utf8",
      env: {
        ...process.env,
        NO_COLOR: "1",
        PATH: `${path.join(dir, "node_modules", ".bin")}${path.delimiter}${process.env.PATH}`,
      },
    });
    output += `$ ${command}\n${result.stdout}${result.stderr}`;
    if (result.status !== 0) {
      return { ok: false, output };
    }
  }
  return { ok: true, output };
}

/*
 * The repository's Python `lib/` ignore rule also matches src/v1/lib/ and the
 * fixtures' lib/ folders; .gitignore re-includes them. `--no-index` checks the
 * rules even for files already tracked.
 */
test("no v1 or fixture file is git-ignored", () => {
  const files = ["src/v1", "test-fixtures"].flatMap((top) =>
    fs
      .readdirSync(path.join(FRONTEND, top), {
        recursive: true,
        withFileTypes: true,
      })
      .filter((d) => d.isFile())
      .map((d) => path.relative(FRONTEND, path.join(d.parentPath, d.name))),
  );
  const result = spawnSync("git", ["check-ignore", "--no-index", "--stdin"], {
    cwd: FRONTEND,
    encoding: "utf8",
    input: files.join("\n"),
  });
  // Exit 1 means "nothing matched"; 0 means some file is ignored.
  assert.equal(result.status, 1, `git-ignored:\n${result.stdout}`);
});

test("every case folder is listed", () => {
  const listed = new Set(CASES.map((c) => c.name).filter(Boolean));
  assert.deepEqual(fs.readdirSync(CASES_DIR).sort(), [...listed].sort());
});

for (const { name, run, fails } of CASES) {
  const label = `${name ?? "empty scaffold"}: ${fails ? "fails" : "passes"} ${run.join(", ")}`;
  test(label, () => {
    const dir = makeTree(name);
    try {
      const { ok, output } = runAll(dir, run);
      if (fails) {
        assert.equal(ok, false, `expected a failure, got:\n${output}`);
        assert.ok(output.includes(fails), `expected "${fails}" in:\n${output}`);
      } else {
        assert.equal(ok, true, output);
      }
    } finally {
      removeTree(dir);
    }
  });
}
