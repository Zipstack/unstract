/*
 * Proves the v1 guardrails fail when they should and pass when they should.
 * Run by `bun run test:v1` with `node --test`: it spawns the real tools, so it
 * is not a vitest test (vitest.config.mjs excludes test-fixtures/).
 *
 * Each case builds a minimal throwaway copy of the frontend (biome.json,
 * package.json, tsconfig.json, vite-env.d.ts, scripts/, the real src/v1
 * scaffold, a node_modules symlink and a .gitignore), overlays the files under
 * cases/<name>/ and runs the real package.json scripts, or a raw command,
 * inside it. The known-bad files live here, outside src/, so CI lint, the
 * pre-commit hook and typecheck never see them.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

const FRONTEND = path.resolve(import.meta.dirname, "..", "..");
const CASES_DIR = path.join(import.meta.dirname, "cases");
const { scripts } = JSON.parse(
  fs.readFileSync(path.join(FRONTEND, "package.json"), "utf8"),
);

/* Rows of "a | b | c" cells; blank lines and "#" comments are skipped. */
function parseTable(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((line) => line.split("|").map((cell) => cell.trim()));
}

const sorted = (items) => items.toSorted((a, b) => a.localeCompare(b));

/*
 * One case per row: the folder under cases/ ("-" for the empty scaffold);
 * the steps, joined by "+", each a package.json script name or a raw command
 * (the v0 side has no v1 script); and a substring the tool output must
 * contain, or "-" when the steps must pass.
 */
const CASES = parseTable(`
  # The empty scaffold passes everything.
  -                              | typecheck:v1 + lint:v1 | -
  # Import boundary, v1 -> v0 (Biome).
  v1-imports-v0-alias            | lint:v1         | v1 imports nothing outside src/v1
  v1-imports-v0-relative         | lint:v1         | v1 imports nothing outside src/v1
  v1-imports-root-absolute       | lint:v1         | v1 imports nothing outside src/v1
  # Import boundary, v0 -> v1: Biome for aliases, check-v1 for the rest.
  v0-imports-v1-internal         | biome lint src/ | v0 may import only the v1 public entry
  v0-imports-v1-relative         | lint:v1         | v0 may import only the v1 public entry
  v0-imports-v1-template         | lint:v1         | v0 may import only the v1 public entry
  v0-imports-v1-entry            | biome lint src/ | -
  # A v1-looking path that is not src/v1 (a package subpath, a v0 folder).
  v0-imports-v1-lookalike        | biome lint src/ + lint:v1 | -
  # v0 typecheck follows the entry into v1, where @v1/... must resolve.
  v0-tsx-imports-entry           | typecheck + typecheck:v1 + lint:v1 | -
  # Banned under v1.
  v1-prop-types                  | lint:v1         | PropTypes are not used
  v1-prop-types-subpath          | lint:v1         | PropTypes are not used
  v1-prop-types-assignment       | lint:v1         | No PropTypes under v1
  v1-antd-import                 | lint:v1         | antd is not used under src/v1
  v1-antd-subpath                | lint:v1         | antd is not used under src/v1
  v1-styles-import-outside       | lint:v1         | v1 styles import nothing outside it
  v1-styles-ant-class            | lint:v1         | No antd 'ant-' class names
  v1-styles-import-antd          | lint:v1         | antd is not used under src/v1
  v1-styles-ant-after-url        | lint:v1         | No antd 'ant-' class names
  v1-unanalysable-import         | lint:v1         | unanalysable import
  v1-component-css-import        | lint:v1         | No component .css under src/v1
  v1-component-css-file          | typecheck:v1    | No component style files
  v1-ant-class-prefix            | lint:v1         | No antd 'ant-' class names
  v1-ant-built-class             | lint:v1         | No antd 'ant-' class names
  v1-explicit-any                | lint:v1         | noExplicitAny
  # The v1 override must add to the shared rules, not replace them.
  v1-base-rules-still-apply      | lint:v1         | noDoubleEquals
  # TypeScript only, strict.
  v1-js-file                     | typecheck:v1    | TypeScript only
  v1-implicit-any                | typecheck:v1    | TS7006
  v1-strict-null                 | typecheck:v1    | TS18048
  v1-unused-local                | typecheck:v1    | TS6133
  v1-unused-parameter            | typecheck:v1    | TS6133
  # Folder taxonomy and contract (the full contract is the matrix below).
  v1-outside-taxonomy            | typecheck:v1    | Outside the v1 folder taxonomy
  v1-root-file                   | typecheck:v1    | Outside the v1 folder taxonomy
  v1-ui-imports-services         | lint:v1         | components/ui/ may not import from services/
  v1-page-imports-other-page     | lint:v1         | pages/projects/ may not import from pages/settings/
  # Only test files may use test/, and being a test file allows nothing else.
  v1-non-test-imports-test       | lint:v1         | components/ui/ may not import from test/
  v1-test-file-imports-services  | lint:v1         | components/ui/ may not import from services/
  v1-allowed-imports             | typecheck:v1 + lint:v1 | -
`).map(([name, run, fails]) => ({
  name: name === "-" ? null : name,
  run: run.split(" + "),
  fails: fails === "-" ? null : fails,
}));

function makeTree(caseName) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v1-boundary-"));
  for (const file of [
    "biome.json",
    "package.json",
    "tsconfig.json",
    "vite-env.d.ts",
  ]) {
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
  // biome.json enables VCS integration with `useIgnoreFile`, which needs an
  // ignore file at the root.
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
    const result = spawnSync("/bin/sh", ["-c", command], {
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
    return output.split("\n").filter((l) => l.startsWith("src/"));
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
      .map((d) => path.relative(FRONTEND, path.join(d.parentPath, d.name)))
      // Cloud plugins copied into src/v1/plugins/<id>/ are git-ignored on
      // purpose; they belong to the cloud repository.
      .filter((rel) => !/^src\/v1\/plugins\/[^/]+\//.test(rel)),
  );
  // A lib/ folder anywhere under v1, not only the top-level one.
  files.push("src/v1/pages/projects/lib/x.ts", "src/v1/lib/sub/lib/x.ts");
  const gitArgs = ["check-ignore", "--no-index", "--stdin"];
  const options = { cwd: FRONTEND, encoding: "utf8", input: files.join("\n") };
  // git from PATH on purpose: this is a developer/CI test, and git has no
  // fixed location across macOS and Linux.
  const result = spawnSync("git", gitArgs, options); // NOSONAR
  // Exit 1 means "nothing matched"; 0 means some file is ignored.
  assert.equal(result.status, 1, `git-ignored:\n${result.stdout}`);
});

test("every case folder is listed", () => {
  const listed = new Set(CASES.map((c) => c.name).filter(Boolean));
  assert.deepEqual(sorted(fs.readdirSync(CASES_DIR)), sorted([...listed]));
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
  assets: "assets",
  plugins: "plugins",
  test: "test",
};
const EVERYTHING = Object.keys(FOLDERS);
const MAY_IMPORT = Object.fromEntries(
  parseTable(`
    app                 | *
    plugins             | *
    test                | *
    pages/a             | components/ui components/patterns shell services stores hooks lib styles assets plugins
    components/ui       | lib styles assets
    components/patterns | components/ui lib services stores hooks assets
    shell               | components/ui components/patterns services stores hooks lib assets
    services            | lib
    stores              | lib
    hooks               | lib
    lib                 |
    styles              | lib assets
    assets              |
  `).map(([from, to]) => [from, to === "*" ? EVERYTHING : to.split(/\s+/)]),
);

/* The file for one folder pair: it imports the target by file and by folder.
 * The entry is a file, so it has only the one form. */
function pairFile(to) {
  const target = FOLDERS[to];
  return to === "entry"
    ? ['import "@v1";']
    : [`import "@v1/${target}/target";`, `import "@v1/${target}";`];
}

/* One file per folder pair, and the problems check-v1 must report for them. */
function contractMatrix() {
  const files = {};
  const expected = [];
  for (const [from, allowed] of Object.entries(MAY_IMPORT)) {
    for (const to of EVERYTHING) {
      const rel = `src/v1/${FOLDERS[from]}/m-${to.replace("/", "-")}.ts`;
      const imports = pairFile(to);
      files[rel] = `${imports.join("\n")}\n`;
      const denied = from !== to && !allowed.includes(to);
      expected.push(
        ...(denied ? imports : []).map(
          (_, i) => `${rel}:${i + 1}: ${from}/ may not import from ${to}/`,
        ),
      );
    }
  }
  return { files, expected };
}

test("folder contract: every folder pair, by file and by folder", () => {
  const { files, expected } = contractMatrix();
  const reported = checkCode(files).map((l) => l.replace(/ \(.*$/, ""));
  assert.deepEqual(sorted(reported), sorted(expected));
});

/* Reported lines for one generated file. */
const linesFor = (reported, file) =>
  reported.filter((l) => l.startsWith(`${file}:`));

test("folder contract: every import form is read", () => {
  // Each file breaks the contract exactly once (components/ui -> services).
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
    templatePrefix:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n: string) => import(`@v1/services/${n}`);",
    require: 'export const a = require("@v1/services/a");',
    newUrl: 'export const a = new URL("@v1/services/a.ts", import.meta.url);',
    relative: 'import { a } from "./../../services/a";',
    afterSlashStarInString:
      'export const route = "/projects/*";\nimport { a } from "@v1/services/a";\n/** doc */',
    afterSlashStarInComment:
      '// matches /api/*\nimport { a } from "@v1/services/a";\n/** doc */',
    afterSlashStarInRegex:
      'export const strip = (p: string) => p.replace(/\\/*$/, "");\nimport { a } from "@v1/services/a";\n/** doc */',
    afterDoubleSlashInString:
      'const u = "a//b"; export { a } from "@v1/services/a";',
    glob: 'export const a = import.meta.glob("@v1/services/*.ts");',
    globArrayLater:
      'export const a = import.meta.glob(["@v1/components/ui/*.tsx", "@v1/services/*.ts"]);',
    afterTemplateExpression:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'const t = `${"}"}/*`;\nimport { a } from "@v1/services/a";\n/** doc */',
  };
  // None of these may be reported: comments, JSX, look-alike class names.
  const quiet = {
    "commentedOut.ts":
      '// import "@v1/services/a";\n/* import("@/helpers/x"); */\nexport const v = 1;',
    "lookalikeClasses.ts": 'export const c = "variant-outline tenant-id";',
    "jsx.tsx":
      'export const T = () => <div className="x">a / b</div>;\nexport const n = 2 / 1;',
  };
  const files = {};
  for (const [form, code] of Object.entries(forms)) {
    files[`src/v1/components/ui/${form}.ts`] = `${code}\n`;
  }
  for (const [name, code] of Object.entries(quiet)) {
    files[`src/v1/components/ui/${name}`] = `${code}\n`;
  }
  const reported = checkCode(files);
  for (const form of Object.keys(forms)) {
    const lines = linesFor(reported, `src/v1/components/ui/${form}.ts`);
    assert.equal(lines.length, 1, `${form}:\n${reported.join("\n")}`);
    assert.ok(
      lines[0].includes("components/ui/ may not import from services/"),
      `${form}: ${lines[0]}`,
    );
  }
  for (const name of Object.keys(quiet)) {
    assert.deepEqual(linesFor(reported, `src/v1/components/ui/${name}`), []);
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
  const imports = [
    "import(`@/helpers/x`)",
    "import(`../helpers/x`)",
    "import(`..`)",
    "import(`./../../helpers/x`)",
    "import(`/src/assets/logo.svg`)",
    "import(`src/helpers/x`)",
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
    "import(`../../helpers/${name}`)",
    'new URL("../../assets/logo.svg", import.meta.url)',
  ];
  const files = {};
  imports.forEach((code, i) => {
    files[`src/v1/lib/outside-${i}.ts`] =
      `export const a = (name: string) => ${code};\n`;
  });
  const reported = checkCode(files);
  imports.forEach((code, i) => {
    const lines = linesFor(reported, `src/v1/lib/outside-${i}.ts`);
    assert.equal(lines.length, 1, `${code}:\n${reported.join("\n")}`);
    assert.ok(lines[0].includes("is outside src/v1"), `${code}: ${lines[0]}`);
  });
});

test("v1: an import the guard cannot read fails closed", () => {
  const files = {
    "src/v1/lib/variable.ts": "export const a = (n: string) => import(n);\n",
    "src/v1/lib/fullyComputed.ts":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n: string) => import(`${n}`);\n",
    "src/v1/components/ui/computedPage.ts":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n: string) => import(`@v1/pages/${n}/index.tsx`);\n",
    // The lazy route registry: app/ may import any v1 folder.
    "src/v1/app/routes.ts":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n: string) => import(`@v1/pages/${n}/index.tsx`);\n",
    // A non-module `new URL` is not an import.
    "src/v1/lib/link.ts":
      'export const u = (p: string) => new URL(p, "https://example.com");\n',
  };
  const reported = checkCode(files);
  for (const file of ["variable", "fullyComputed"]) {
    const lines = linesFor(reported, `src/v1/lib/${file}.ts`);
    assert.equal(lines.length, 1, reported.join("\n"));
    assert.ok(lines[0].includes("unanalysable import"), lines[0]);
  }
  const page = linesFor(reported, "src/v1/components/ui/computedPage.ts");
  assert.equal(page.length, 1, reported.join("\n"));
  assert.ok(page[0].includes("may not import a computed v1 path"), page[0]);
  assert.deepEqual(linesFor(reported, "src/v1/app/routes.ts"), []);
  assert.deepEqual(linesFor(reported, "src/v1/lib/link.ts"), []);
});

test("v0 reaches v1 only through @v1, in any form", () => {
  const denied = {
    "static.jsx": 'import x from "@v1/lib/x";',
    "template.jsx": "export const a = () => import(`@v1/plugins/manifest`);",
    "templatePrefix.jsx":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n) => import(`../v1/lib/${n}`);",
    "glob.jsx": 'export const a = import.meta.glob("@v1/pages/*/index.ts");',
    "globRootAbsolute.jsx":
      'export const a = import.meta.glob("/src/v1/lib/*.ts");',
    "globArrayLater.jsx":
      'export const a = import.meta.glob(["./*.jsx", "../v1/lib/*.ts"]);',
    "require.jsx": 'export const a = require("../v1/lib/x");',
    "newUrl.jsx":
      'export const a = new URL("../v1/lib/x.ts", import.meta.url);',
    "aliasV0.jsx": 'export const a = () => import("@/v1/lib/x");',
    "aliasV0Dot.jsx": "export const a = () => import(`@/./v1/lib/x`);",
    "srcPath.jsx": 'export const a = () => import("src/v1/lib/x");',
    "relativeEntry.jsx": 'import "../v1";',
    "typed.tsx": 'import x from "../v1/lib/x";\nexport const y = x;',
    "styles.css": '@import "../v1/styles/tokens.css";',
    "stylesRootAbsolute.css": ".a { background: url(/src/v1/styles/a.png); }",
  };
  const allowed = {
    "entry.jsx": 'import "@v1";',
    "entryTemplate.jsx": "export const a = () => import(`@v1`);",
    "entryIndex.jsx": 'import "@v1/index";',
    "v0Only.jsx": 'import x from "../helpers/x";\nexport const y = x;',
    "lookalike.jsx":
      'import a from "@/api/v1";\nimport { v1 } from "uuid/v1";\nexport const b = [a, v1];',
  };
  const files = {};
  for (const [name, code] of Object.entries({ ...denied, ...allowed })) {
    files[`src/pages/${name}`] = `${code}\n`;
  }
  const reported = checkCode(files);
  for (const name of Object.keys(denied)) {
    const lines = linesFor(reported, `src/pages/${name}`);
    assert.equal(lines.length, 1, `${name}:\n${reported.join("\n")}`);
    assert.ok(lines[0].includes("reaches into src/v1"), `${name}: ${lines[0]}`);
  }
  for (const name of Object.keys(allowed)) {
    assert.deepEqual(linesFor(reported, `src/pages/${name}`), [], name);
  }
});
