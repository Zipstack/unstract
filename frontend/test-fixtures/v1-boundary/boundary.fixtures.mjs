/*
 * Proves the v1 guardrails fail when they should and pass when they should.
 * Run by `bun run test:v1` with `node --test`: it spawns the real tools, so it
 * is not a vitest test (vitest.config.mjs excludes test-fixtures/).
 *
 * Each case builds a minimal throwaway copy of the frontend (biome.json,
 * package.json, vite-env.d.ts, scripts/, the real src/v1 scaffold, a
 * node_modules symlink and a git root), overlays the files under
 * cases/<name>/ and runs the real package.json scripts, or a raw command,
 * inside it. The known-bad files live here, outside src/, so CI lint, the
 * pre-commit hook and typecheck never see them.
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
 * which has no v1 script. `fails` is a substring the tool output must
 * contain; cases without it must pass.
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
  {
    name: "v1-imports-root-absolute",
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
    name: "v1-antd-import",
    run: ["lint:v1"],
    fails: "antd is not used under src/v1",
  },
  {
    name: "v1-antd-subpath",
    run: ["lint:v1"],
    fails: "antd is not used under src/v1",
  },
  {
    name: "v1-prop-types-subpath",
    run: ["lint:v1"],
    fails: "PropTypes are not used",
  },
  {
    name: "v1-styles-import-outside",
    run: ["lint:v1"],
    fails: "v1 styles import nothing outside it",
  },
  {
    name: "v1-styles-ant-class",
    run: ["lint:v1"],
    fails: "No antd 'ant-' class names",
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
  {
    name: "v1-ant-built-class",
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
    fails: "TS7006",
  },
  {
    name: "v1-strict-null",
    run: ["typecheck:v1"],
    fails: "TS18048",
  },
  {
    name: "v1-unused-local",
    run: ["typecheck:v1"],
    fails: "TS6133",
  },
  {
    name: "v1-unused-parameter",
    run: ["typecheck:v1"],
    fails: "TS6133",
  },

  // Folder taxonomy and contract (the full contract is the matrix below).
  {
    name: "v1-outside-taxonomy",
    run: ["typecheck:v1"],
    fails: "Outside the v1 folder taxonomy",
  },
  {
    name: "v1-root-file",
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
  // Only test files may use test/, and being a test file allows nothing else.
  {
    name: "v1-non-test-imports-test",
    run: ["lint:v1"],
    fails: "components/ui/ may not import from test/",
  },
  {
    name: "v1-test-file-imports-services",
    run: ["lint:v1"],
    fails: "components/ui/ may not import from services/",
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

function writeFile(dir, rel, content) {
  const file = path.join(dir, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

/*
 * Runs the steps in order, stopping at the first failure. `output` holds only
 * what the tools printed, so an expected message can never match the command
 * text. A command that could not start at all is an error, not a "failure".
 */
function runAll(dir, run) {
  let output = "";
  let log = "";
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
    if (result.error || result.status === null) {
      throw new Error(
        `could not run "${command}": ${result.error ?? result.signal}`,
      );
    }
    // 127: sh could not find the command, e.g. a tool missing from PATH.
    assert.notEqual(result.status, 127, `command not found: ${command}`);
    output += result.stdout + result.stderr;
    log += `$ ${command}\n${result.stdout}${result.stderr}`;
    if (result.status !== 0) {
      return { ok: false, output, log };
    }
  }
  return { ok: true, output, log };
}

/* Runs `check-v1.mjs --code` over generated files; returns the reported lines. */
function checkCode(files) {
  const dir = makeTree(null);
  try {
    for (const [rel, content] of Object.entries(files)) {
      writeFile(dir, rel, content);
    }
    const { output } = runAll(dir, ["node scripts/check-v1.mjs --code"]);
    return output.split("\n").filter((l) => l.startsWith("src/v1/"));
  } finally {
    removeTree(dir);
  }
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
      .filter((d) => d.isFile() && d.name !== ".DS_Store")
      .map((d) => path.relative(FRONTEND, path.join(d.parentPath, d.name))),
  );
  // A lib/ folder anywhere under v1, not only the top-level one.
  files.push("src/v1/pages/projects/lib/x.ts", "src/v1/lib/sub/lib/x.ts");
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
      const { ok, output, log } = runAll(dir, run);
      if (fails) {
        assert.equal(ok, false, `expected a failure, got:\n${log}`);
        assert.ok(output.includes(fails), `expected "${fails}" in:\n${log}`);
      } else {
        assert.equal(ok, true, log);
      }
    } finally {
      removeTree(dir);
    }
  });
}

/*
 * The folder contract, written out independently of check-v1.mjs so a typo
 * in either shows up here. Source: the table in src/v1/README.md. Folders
 * may always import themselves; pages/a and pages/b stand for two pages.
 */
const FOLDERS = {
  entry: "",
  app: "app",
  "components/ui": "components/ui",
  "components/patterns": "components/patterns",
  shell: "shell",
  "pages/a": "pages/a",
  "pages/b": "pages/b",
  services: "services",
  stores: "stores",
  hooks: "hooks",
  lib: "lib",
  styles: "styles",
  plugins: "plugins",
  test: "test",
};
const EVERYTHING = Object.keys(FOLDERS);
const MAY_IMPORT = {
  app: EVERYTHING,
  plugins: EVERYTHING,
  test: EVERYTHING,
  "pages/a": [
    "components/ui",
    "components/patterns",
    "shell",
    "services",
    "stores",
    "hooks",
    "lib",
    "styles",
    "plugins",
  ],
  "components/ui": ["lib", "styles"],
  "components/patterns": [
    "components/ui",
    "lib",
    "services",
    "stores",
    "hooks",
  ],
  shell: [
    "components/ui",
    "components/patterns",
    "services",
    "stores",
    "hooks",
    "lib",
  ],
  services: ["lib"],
  stores: ["lib"],
  hooks: ["lib"],
  lib: [],
  styles: ["lib"],
};

test("folder contract: every folder pair, by file and by folder", () => {
  const files = {};
  const expected = [];
  for (const [from, allowed] of Object.entries(MAY_IMPORT)) {
    for (const to of EVERYTHING) {
      const rel = `src/v1/${FOLDERS[from]}/m-${to.replace("/", "-")}.ts`;
      // The entry is a file, so it has only the one form.
      files[rel] =
        to === "entry"
          ? 'import "@v1";\n'
          : `import "@v1/${FOLDERS[to]}/target";\nimport "@v1/${FOLDERS[to]}";\n`;
      if (from !== to && !allowed.includes(to)) {
        const lines = to === "entry" ? [1] : [1, 2];
        for (const line of lines) {
          expected.push(`${rel}:${line}: ${from}/ may not import from ${to}/`);
        }
      }
    }
  }
  const reported = checkCode(files).map((l) => l.replace(/ \(.*$/, ""));
  assert.deepEqual(reported.sort(), expected.sort());
});

test("folder contract: every import form is read", () => {
  // Each file breaks the contract once (components/ui -> services).
  const forms = {
    static: 'import { a } from "@v1/services/a";',
    multiline: 'import {\n  a,\n  b,\n} from "@v1/services/a";',
    type: 'import type { A } from "@v1/services/a";',
    inlineType: 'import { type A } from "@v1/services/a";',
    sideEffect: 'import "@v1/services/a";',
    namespace: 'import * as a from "@v1/services/a";',
    exportFrom: 'export { a } from "@v1/services/a";',
    exportStar: 'export * from "@v1/services/a";',
    exportStarAs: 'export * as a from "@v1/services/a";',
    dynamic: 'export const a = () => import("@v1/services/a");',
    dynamicTemplate: "export const a = () => import(`@v1/services/a`);",
    require: 'export const a = require("@v1/services/a");',
    relative: 'import { a } from "./../../services/a";',
    afterSlashStarInString:
      'export const route = "/projects/*";\nimport { a } from "@v1/services/a";\n/** doc */',
    afterSlashStarInComment:
      '// matches /api/*\nimport { a } from "@v1/services/a";\n/** doc */',
    afterDoubleSlashInString:
      'const u = "a//b"; export { a } from "@v1/services/a";',
    glob: 'export const a = import.meta.glob("@v1/services/*.ts");',
    afterTemplateExpression:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'const t = `${"}"}/*`;\nimport { a } from "@v1/services/a";\n/** doc */',
  };
  const files = {};
  for (const [form, code] of Object.entries(forms)) {
    files[`src/v1/components/ui/${form}.ts`] = `${code}\n`;
  }
  const reported = checkCode(files);
  for (const form of Object.keys(forms)) {
    const file = `src/v1/components/ui/${form}.ts:`;
    assert.ok(
      reported.some((l) => l.startsWith(file)),
      `${form}: not reported\n${reported.join("\n")}`,
    );
  }
});

test("a symlinked file under v1 fails typecheck:v1", () => {
  const dir = makeTree(null);
  try {
    fs.symlinkSync(
      path.join(dir, "vite-env.d.ts"),
      path.join(dir, "src", "v1", "lib", "linked.d.ts"),
    );
    const { ok, output, log } = runAll(dir, ["typecheck:v1"]);
    assert.equal(ok, false, log);
    assert.ok(output.includes("No symlinks under v1"), log);
  } finally {
    removeTree(dir);
  }
});

test("v1 imports nothing outside src/v1, in any spelling", () => {
  const specs = [
    "@/helpers/x",
    "../helpers/x",
    "..",
    "./../../helpers/x",
    "/src/assets/logo.svg",
    "src/helpers/x",
  ];
  const files = {};
  specs.forEach((spec, i) => {
    files[`src/v1/lib/outside-${i}.ts`] =
      `export const a = () => import(\`${spec}\`);\n`;
  });
  const reported = checkCode(files);
  specs.forEach((spec, i) => {
    assert.ok(
      reported.some(
        (l) =>
          l.startsWith(`src/v1/lib/outside-${i}.ts:`) &&
          l.includes("is outside src/v1"),
      ),
      `'${spec}': not reported\n${reported.join("\n")}`,
    );
  });
});
