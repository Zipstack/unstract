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
  # Import boundary, v0 -> v1: Biome for plain spellings, check-v1 for all.
  v0-imports-v1-internal         | biome lint src/ | v0 may import only the v1 public entry
  v0-imports-v1-relative         | biome lint src/ | v0 may import only the v1 public entry
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
  v1-antd-icons                  | lint:v1         | antd is not used under src/v1
  # Lucide is the only icon library (an allowlist), with canonical names only.
  v1-icon-library                | lint:v1         | Lucide is the only icon library under src/v1
  v1-icon-library-subpath        | lint:v1         | Lucide is the only icon library under src/v1
  v1-icon-library-unlisted       | lint:v1         | '@iconify/react' is not allowed
  v1-icon-library-lucide-static  | lint:v1         | 'lucide-static/icons/loader-circle.svg' is not allowed
  v1-icon-library-feather        | lint:v1         | 'react-feather' is not allowed
  v1-icon-library-mdi            | lint:v1         | '@mdi/js' is not allowed
  v1-icon-library-flags          | lint:v1         | Lucide is the only icon library under src/v1
  v1-feature-flag-sdk            | lint:v1         | -
  v1-icon-library-css            | lint:v1         | 'flag-icons/css/flag-icons.min.css' is not allowed
  v1-icon-library-scss-tilde     | lint:v1         | '@fortawesome/fontawesome-free/scss/fontawesome' is not allowed
  # Biome's own warning stops lint:v1 first; check-v1-icons still catches it.
  v1-icon-library-css-escaped    | lint:v1         | noUselessEscapeInString
  v1-icon-library-css-escaped    | node scripts/check-v1-icons.mjs | '@fortawesome/fontawesome-free/css/all.min.css' is not allowed
  v1-lucide-subpath              | lint:v1         | not 'lucide-react/dynamic'
  v1-lucide-alias                | lint:v1         | Deprecated lucide-react alias 'Loader2'
  v1-lucide-alias-uncommon       | lint:v1         | import the canonical name 'CircleQuestionMark'
  v1-lucide-alias-suffixed       | lint:v1         | Deprecated lucide-react alias 'LucideLoader2'
  v1-lucide-namespace            | lint:v1         | not as a namespace or default import
  v1-lucide-dynamic-template     | lint:v1         | a dynamic import or
  v1-lucide-icons-map            | lint:v1         | it is keyed by name, deprecated aliases included
  v1-lucide-canonical            | lint:v1         | -
  v1-styles-import-outside       | lint:v1         | v1 styles import nothing outside it
  v1-styles-ant-class            | lint:v1         | No antd 'ant-' class names
  v1-styles-import-antd          | lint:v1         | antd is not used under src/v1
  v1-styles-ant-after-url        | lint:v1         | No antd 'ant-' class names
  v1-unanalysable-import         | lint:v1         | unanalysable import
  v1-component-css-import        | lint:v1         | No component .css under src/v1
  v1-component-css-file          | typecheck:v1    | No component style files
  # Every CSS language Vite knows, not only .css.
  v1-component-pcss-file         | typecheck:v1    | No component style files
  v1-component-pcss-import       | lint:v1         | No component .css under src/v1
  # A file type outside the allowlist (Vite can load it with ?worker).
  v1-unknown-file-type           | typecheck:v1    | Unknown file type under v1
  v1-ant-class-prefix            | lint:v1         | No antd 'ant-' class names
  v1-ant-built-class             | lint:v1         | No antd 'ant-' class names
  # One notification entry point: toast libraries only in components/ui/feedback/.
  v1-notify-sonner               | lint:v1         | One notification entry point in v1
  v1-notify-radix-toast          | lint:v1         | One notification entry point in v1
  v1-notify-radix-namespace      | lint:v1         | One notification entry point in v1
  v1-notify-dynamic              | lint:v1         | One notification entry point in v1
  v1-notify-radix-dynamic        | lint:v1         | One notification entry point in v1
  # Biome's own warning stops lint:v1 first; check-v1 still catches it.
  v1-notify-radix-bracket        | lint:v1         | noDynamicNamespaceImportAccess
  v1-notify-radix-bracket        | node scripts/check-v1.mjs --code | One notification entry point in v1
  v1-notify-radix-jsx            | lint:v1         | One notification entry point in v1
  v1-notify-radix-require        | lint:v1         | One notification entry point in v1
  v1-notify-radix-reexport       | lint:v1         | One notification entry point in v1
  v1-notify-radix-then           | lint:v1         | One notification entry point in v1
  # Outside the feedback folder, a static named radix-ui import without Toast is fine.
  v1-notify-radix-named-ok       | lint:v1         | -
  v1-notify-feedback-ok          | lint:v1         | -
  v1-explicit-any                | lint:v1         | noExplicitAny
  # The v1 override must add to the shared rules, not replace them.
  v1-base-rules-still-apply      | lint:v1         | noDoubleEquals
  # TypeScript only, strict.
  v1-js-file                     | typecheck:v1    | TypeScript only
  v1-implicit-any                | typecheck:v1    | TS7006
  v1-strict-null                 | typecheck:v1    | TS18048
  v1-unused-local                | typecheck:v1    | TS6133
  v1-unused-parameter            | typecheck:v1    | TS6133
  # No @/ path in src/v1/tsconfig.json, so tsc rejects the v0 alias too.
  v1-tsc-v0-alias                | typecheck:v1    | TS2307
  # Folder taxonomy and contract (the full contract is the matrix below).
  v1-outside-taxonomy            | typecheck:v1    | Outside the v1 folder taxonomy
  v1-root-file                   | typecheck:v1    | Outside the v1 folder taxonomy
  v1-ui-imports-services         | lint:v1         | components/ui/ may not import from services/
  v1-page-imports-other-page     | lint:v1         | pages/projects/ may not import from pages/settings/
  # Only test files may use test/, and being a test file allows nothing else.
  v1-non-test-imports-test       | lint:v1         | components/ui/ may not import from test/
  v1-test-file-imports-services  | lint:v1         | components/ui/ may not import from services/
  v1-allowed-imports             | typecheck:v1 + lint:v1 | -
  # Styling policy (check-v1-styles.mjs)
  v1-inline-style                | lint:v1         | No inline style under v1
  v1-inline-style-variable       | lint:v1         | No inline style under v1
  v1-inline-style-mixed          | lint:v1         | No inline style under v1
  v1-inline-style-spaced         | lint:v1         | No inline style under v1
  v1-inline-style-custom-props-ok | typecheck:v1 + lint:v1 | -
  v1-raw-colour-palette          | lint:v1         | No raw colour under v1
  v1-raw-colour-arbitrary        | lint:v1         | No raw colour under v1
  v1-raw-colour-prop             | lint:v1         | No raw colour under v1
  v1-raw-colour-named            | lint:v1         | No raw colour under v1
  v1-raw-colour-named-prop       | lint:v1         | No raw colour under v1
  v1-raw-pixel-arbitrary         | lint:v1         | No raw pixel value under v1
  v1-raw-pixel-arbitrary-multi   | lint:v1         | No raw pixel value under v1
  v1-raw-pixel-arbitrary-separator | lint:v1       | No raw pixel value under v1
  v1-important-utility           | lint:v1         | No !important under v1
  v1-important-variant-utility   | lint:v1         | No !important under v1
  # Biome now reports CSS !important first (warnings fail v1), so the styling
  # policy's own CSS branch is run directly as well.
  v1-important-css               | lint:v1         | noImportantStyles
  v1-important-css               | node scripts/check-v1-styles.mjs | No !important under v1
  v1-css-import-from-page        | lint:v1         | CSS is imported only from app/ and styles/
  v1-styles-raw-colour           | lint:v1         | No raw colour under v1
  v1-styles-raw-colour-named     | lint:v1         | No raw colour under v1
  v1-styles-raw-viewport-unit    | lint:v1         | No raw pixel value under v1
  v1-styles-unscoped-selector    | lint:v1         | Every v1 selector is scoped to .v1
  v1-styles-sibling-selector     | lint:v1         | selects outside it
  v1-styles-nested-sibling-selector | lint:v1      | selects outside it
  v1-styles-color-scheme-media   | lint:v1         | prefers-color-scheme
  v1-unprefixed-utility          | lint:v1         | No unprefixed Tailwind utility under v1
  v1-unprefixed-single-class     | lint:v1         | No unprefixed Tailwind utility under v1
  v1-prefix-after-variant        | lint:v1         | The ui: prefix comes first
  v1-cva-unprefixed-variant      | lint:v1         | No unprefixed Tailwind utility under v1
  v1-styles-policy-ok            | lint:v1         | -
  v1-plain-strings-ok            | lint:v1         | -
  # Quality (P0-T10): accessibility rules, and every other warning, fail v1.
  # Plain biome lint fails only on errors, so this proves the v1 override.
  v1-a11y-button-type            | biome lint src/v1/ | useButtonType
  v1-warning-is-error            | lint:v1         | noArrayIndexKey
  # Purity (P0-T10): the antd shims are v0, so v1 cannot reach them.
  v1-imports-v0-shim             | lint:v1         | v1 imports nothing outside src/v1
  # Seam (P0-T10, check-v1-seam.mjs): v1 work changes v0 only at the seam.
  seam-v1-only                   | node scripts/check-v1-seam.mjs --changed changed.txt | -
  seam-v1-at-the-seam            | node scripts/check-v1-seam.mjs --changed changed.txt | -
  seam-v0-fix-only               | node scripts/check-v1-seam.mjs --changed changed.txt | -
  seam-v1-changes-v0-page        | node scripts/check-v1-seam.mjs --changed changed.txt | src/pages/LogsPage.jsx: changes v0 outside the seam
  seam-v1-changes-public         | node scripts/check-v1-seam.mjs --changed changed.txt | public/favicon.ico: changes v0 outside the seam
  seam-v1-tooling-changes-v0     | node scripts/check-v1-seam.mjs --changed changed.txt | antd-button.tsx: changes v0 outside the seam
  seam-v1-changes-v0-page        | node scripts/check-v1-seam.mjs --changed changed.txt --override | -
  # The allowlist globs: nested matches pass, near-misses do not.
  seam-glob-nested               | node scripts/check-v1-seam.mjs --changed changed.txt | -
  seam-glob-near-misses          | node scripts/check-v1-seam.mjs --changed changed.txt | frontend/src/routes.jsx: changes v0
  seam-glob-near-misses          | node scripts/check-v1-seam.mjs --changed changed.txt | frontend/src/indexXcss: changes v0
  seam-glob-near-misses          | node scripts/check-v1-seam.mjs --changed changed.txt | frontend/src/pages/src/App.jsx: changes v0
  seam-glob-near-misses          | node scripts/check-v1-seam.mjs --changed changed.txt | frontend/src/routesX/a.jsx: changes v0
  # A top-level v1 file (vitest.v1.config.mts) is v1 work.
  seam-v1-root-config            | node scripts/check-v1-seam.mjs --changed changed.txt | frontend/src/pages/a.jsx: changes v0
  # --base, as CI runs it: a real repository, root one level above frontend/.
  seam-git-v1-changes-v0         | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/src/pages/a.jsx: changes v0
  seam-git-renames-v0            | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/src/pages/a.jsx: changes v0
  seam-git-deletes-v0            | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/src/pages/a.jsx: changes v0
  seam-git-non-ascii             | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/src/pages/Überblick.jsx: changes v0
  seam-git-changes-index-html    | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/index.html: changes v0
  seam-git-at-the-seam           | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | -
  # The allowlist comes from the base, so widening it in the PR does not help.
  seam-git-widens-allowlist      | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base base | frontend/src/pages/a.jsx: changes v0
  seam-git-v1-changes-v0         | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-seam.mjs --base nope | git diff against 'nope' failed
  # Separation (P0-T10, check-v1-separation.mjs): no plugin code in OSS.
  -                              | node scripts/check-v1-separation.mjs | -
  v1-plugin-folder               | node scripts/check-v1-separation.mjs | src/v1/plugins/acme/: enterprise plugin code
  # In git, as CI runs it: only tracked files count.
  -                              | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-separation.mjs | -
  separation-git-overlay-ignored | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-separation.mjs | -
  separation-git-plugin-committed | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-separation.mjs | src/v1/plugins/acme/: enterprise plugin code
  separation-git-non-ascii-file  | sh "$V1_FIXTURES/git-case.sh" node scripts/check-v1-separation.mjs | -
  # Bundle (P0-T10, check-v1-bundle.mjs): real builds, then a saved report.
  bundle-v1-clean                | node scripts/check-v1-bundle.mjs | -
  # A package v0 also uses is not v0 code, wherever Rollup places it.
  bundle-v1-shares-package       | node scripts/check-v1-bundle.mjs | -
  bundle-v1-pulls-v0             | node scripts/check-v1-bundle.mjs | reaches v0 module src/legacy.js
  bundle-v1-dynamic-v0           | node scripts/check-v1-bundle.mjs | reaches v0 module src/legacy.js
  # Through a CommonJS module, which Rollup reaches via a virtual \0 module.
  bundle-v1-cjs-v0               | node scripts/check-v1-bundle.mjs | reaches v0 module src/legacy.cjs
  # Mounted statically, so v1 is inlined into a v0 chunk and has none of its own.
  bundle-v1-static-mount         | node scripts/check-v1-bundle.mjs | src/v1/lib/text.ts (v1) reaches v0 module src/legacy.js
  # antd reached through a package, which only this guard can see.
  bundle-v1-antd-report          | node scripts/check-v1-bundle.mjs --report report.json | reaches antd module /repo/frontend/node_modules/antd/es/button/index.js through /repo/frontend/node_modules/some-table/index.js
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
  // Without a local copy of the cloud overlay (ignored by design, D7), so a
  // developer who has one gets the same results as CI.
  const plugins = path.join(FRONTEND, "src", "v1", "plugins");
  fs.cpSync(path.join(FRONTEND, "src", "v1"), path.join(dir, "src", "v1"), {
    recursive: true,
    filter: (src) =>
      path.dirname(src) !== plugins || !fs.statSync(src).isDirectory(),
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
        // For steps that run git-case.sh, which is not copied into the tree.
        V1_FIXTURES: import.meta.dirname,
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
/* The files among `files` (relative to frontend/) that git ignores. */
function gitIgnored(files) {
  const gitArgs = ["check-ignore", "--no-index", "--stdin"];
  const options = { cwd: FRONTEND, encoding: "utf8", input: files.join("\n") };
  // git from PATH on purpose: this is a developer/CI test, and git has no
  // fixed location across macOS and Linux.
  const result = spawnSync("git", gitArgs, options); // NOSONAR
  // Exit 0: some file is ignored; 1: none is; anything else is an error.
  assert.ok(result.status === 0 || result.status === 1, result.stderr);
  return result.stdout.split("\n").filter(Boolean);
}

// Where the cloud build copies its v1 plugins; git-ignored on purpose.
const CLOUD_V1_PLUGIN = /^src\/v1\/plugins\/[^/]+\//;

test("no v1 or fixture file is git-ignored", () => {
  const files = ["src/v1", "test-fixtures"].flatMap((top) =>
    fs
      .readdirSync(path.join(FRONTEND, top), {
        recursive: true,
        withFileTypes: true,
      })
      .filter((d) => d.isFile() && d.name !== ".DS_Store")
      .map((d) => path.relative(FRONTEND, path.join(d.parentPath, d.name)))
      // A local copy of the cloud plugins, if any, is ignored by design.
      .filter((rel) => !CLOUD_V1_PLUGIN.test(rel)),
  );
  // A lib/ folder anywhere under v1, not only the top-level one.
  files.push("src/v1/pages/projects/lib/x.ts", "src/v1/lib/sub/lib/x.ts");
  assert.deepEqual(gitIgnored(files), []);
});

test("cloud v1 plugins are git-ignored; the public manifest is not", () => {
  const cloud = [
    "src/v1/plugins/billing/index.ts",
    "src/v1/plugins/billing/lib/x.ts",
    "src/v1/plugins/stray.ts",
  ];
  const ignored = gitIgnored([...cloud, "src/v1/plugins/manifest.ts"]);
  assert.deepEqual(sorted(ignored), sorted(cloud));
});

// The accessibility rules the v1 README and the PR promise as errors.
const V1_A11Y_ERRORS = [
  "noLabelWithoutControl",
  "noNoninteractiveElementInteractions",
  "noRedundantRoles",
  "noStaticElementInteractions",
  "useAriaPropsSupportedByRole",
  "useButtonType",
  "useFocusableInteractive",
  "useGenericFontNames",
  "useKeyWithClickEvents",
  "useSemanticElements",
  "useValidAnchor",
];

test("the accessibility rules are errors under src/v1", () => {
  const biome = JSON.parse(
    fs.readFileSync(path.join(FRONTEND, "biome.json"), "utf8"),
  );
  const v1 = biome.overrides.find((o) => o.includes?.includes("src/v1/**"));
  assert.ok(v1, "biome.json has no src/v1/** override");
  const a11y = v1.linter?.rules?.a11y ?? {};
  for (const rule of V1_A11Y_ERRORS) {
    assert.equal(a11y[rule], "error", `a11y/${rule} under src/v1`);
  }
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
    // An apostrophe in JSX text is not a string opener.
    afterJsxContraction:
      'export const A = () => <span>It\'s <button onClick={() => import("@v1/services/a")}>ready</button></span>;',
    afterJsxBraceApostrophe:
      'export const B = (n: string) => <p>{n}\'s <b onClick={() => import("@v1/services/a")}>x</b></p>;',
    globArrayLater:
      'export const a = import.meta.glob(["@v1/components/ui/*.tsx", "@v1/services/*.ts"]);',
    afterTemplateExpression:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'const t = `${"}"}/*`;\nimport { a } from "@v1/services/a";\n/** doc */',
    // JSX text and attributes that a hand-written tokenizer misread (PR #2380).
    afterJsxDivisionText:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'export const P = (p: { d: number; t: number; x: string }) => <p>{p.d}/{p.t} {String(`progress/${p.x}`)}</p>;\nexport const later = () => import("@v1/services/a");',
    afterJsxSlashStarText:
      'export const Q = () => <p>files/*.ts <code>src/*</code></p>;\nexport const later = () => import("@v1/services/a");',
    afterJsxBacktickText:
      'export const R = () => <p>Press ` to open</p>;\nexport const later = () => import("@v1/services/a");',
    afterJsxSelfClosingTag:
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'export const A = (p: { x: string; id: string }) => (\n  <div>``<img src={p.x} />`` <a href={`/b/${p.id}`}>b</a></div>\n);\nexport const later = () => import("@v1/services/a");',
    afterMultilineAttribute:
      'export const B = () => (\n  <button title="Matches /api/*\n" onClick={() => import("@v1/services/a")}>b</button>\n);',
    divisionAfterFrom:
      'export const r = async (range: { from: number }) => range.from / (await import("@v1/services/a")).rate;',
    escapedSpecifier: 'import { a } from "@v1\\/services/a";\nexport { a };',
    stringNamedBinding:
      'import { "a-b" as c } from "@v1/services/a";\nexport { c };',
    typeofImport: 'export type A = typeof import("@v1/services/a");',
    importEquals: 'import a = require("@v1/services/a");\nexport { a };',
    // TypeScript wrappers around the specifier (Greptile, PR #2380).
    asConst: 'export const a = () => import("@v1/services/a" as const);',
    satisfies:
      'export const a = () => import(("@v1/services/a" satisfies string));',
    // Wrappers around the parts that mark an import (vishnuszipstack, #2380).
    newUrlMetaAs:
      'export const a = new URL("@v1/services/a.ts", import.meta.url as string);',
    globCalleeAs:
      'export const a = (import.meta.glob as never as (p: string) => unknown)("@v1/services/*.ts");',
    requireCalleeAs:
      'export const a = (require as (s: string) => unknown)("@v1/services/a");',
    newUrlCalleeAs:
      'export const a = new (URL as typeof URL)("@v1/services/a.ts", import.meta.url);',
    // A conditional stands for both branches; lib/ is allowed, services/ not.
    conditional:
      'export const a = (c: boolean) => import(c ? "@v1/services/a" : "@v1/lib/x");',
    // Vite resolves relative glob patterns against `base`.
    globBase:
      'export const a = import.meta.glob("./*.ts", { base: "@v1/services" });',
  };
  // None of these may be reported: comments, JSX, look-alike class names.
  const quiet = {
    "commentedOut.ts":
      '// import "@v1/services/a";\n/* import("@/helpers/x"); */\nexport const v = 1;',
    "lookalikeClasses.ts": 'export const c = "variant-outline tenant-id";',
    // Example source text in strings, templates and regexes is not an import.
    "importsInStrings.ts":
      'export const a = "import(name)";\nexport const b = \'import x from "@/helpers/x"\';\nexport const c = `require(n) or import.meta.glob(x)`;\nexport const d = /import\\(x\\)/;',
    "jsxQuotes.tsx":
      "export const C = () => <p title=\"It's fine\">Don't 'quote' me</p>;",
    "jsx.tsx":
      'export const T = () => <div className="x">a / b</div>;\nexport const n = 2 / 1;',
    "jsxText.tsx":
      "export const J = (p: { d: number; t: number }) => <p>{p.d}/{p.t} files/*.ts <code>src/*</code> Press ` to open</p>;",
    "importProse.tsx":
      "export const P = () => <p>You can import (or export) projects.</p>;",
    // Methods named import/require are not module loads.
    "memberCalls.ts":
      "export const f = (api: { import(f: string): void; require(f: string): void }, s: string) => {\n  api.import(s);\n  api.require(s);\n};\nexport class X {\n  import(f: string) {\n    return f;\n  }\n}",
    "packageImport.ts":
      'import { useState } from "react";\nexport const u = useState;',
    // Syntax only a declaration file may hold.
    "declarations.d.ts":
      "export const version: string;\nexport function f(a: number): void;",
    // `base` applies to relative patterns only.
    "globBaseAlias.ts":
      'export const a = import.meta.glob("@v1/lib/*.ts", { base: "../../services" });',
  };
  const files = {};
  for (const [form, code] of Object.entries(forms)) {
    files[`src/v1/components/ui/${form}.tsx`] = `${code}\n`;
  }
  for (const [name, code] of Object.entries(quiet)) {
    files[`src/v1/components/ui/${name}`] = `${code}\n`;
  }
  const reported = checkCode(files);
  for (const form of Object.keys(forms)) {
    const lines = linesFor(reported, `src/v1/components/ui/${form}.tsx`);
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

/* Puts each import in its own src/v1/lib/ file and asserts each file is
 * reported exactly once, with `message`. */
function expectEachReported(stem, imports, message) {
  const files = {};
  imports.forEach((code, i) => {
    files[`src/v1/lib/${stem}-${i}.ts`] =
      `export const a = (name: string) => ${code};\n`;
  });
  const reported = checkCode(files);
  imports.forEach((code, i) => {
    const lines = linesFor(reported, `src/v1/lib/${stem}-${i}.ts`);
    assert.equal(lines.length, 1, `${code}:\n${reported.join("\n")}`);
    assert.ok(lines[0].includes(message), `${code}: ${lines[0]}`);
  });
}

test("v1 imports nothing outside src/v1, in any spelling", () => {
  const imports = [
    "import(`@/helpers/x`)",
    "import(`../../helpers/x`)",
    "import(`../..`)",
    "import(`./../../helpers/x`)",
    "import(`/src/assets/logo.svg`)",
    "import(`src/helpers/x`)",
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
    "import(`../../helpers/${name}`)",
    'new URL("../../assets/logo.svg", import.meta.url)',
    'new URL("../../assets/logo.svg", import.meta.url as string)',
    'import.meta.glob("./*.js", { base: "../../components" })',
    'import.meta.glob("./*.js", { base: "/src/helpers" })',
  ];
  expectEachReported("outside", imports, "is outside src/v1");
});

test("v1: a '../' that stays inside v1 is reported as such", () => {
  const imports = [
    'import("../lib/x")',
    "import(`..`)",
    'import("../helpers/x")',
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
    "import(`../lib/${name}`)",
  ];
  expectEachReported("climbs", imports, "climbs with '../'");
});

test("v1: a '..' after a wildcard or template hole is reported", () => {
  const imports = [
    'import.meta.glob("./*/../../../helpers/*.js")',
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
    "import(`./${name}/../../../helpers/x.js`)",
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
    "import(`@v1/lib/${name}..`)",
  ];
  expectEachReported("later", imports, "has '..' after a wildcard");
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
    "src/v1/lib/concatenation.ts":
      'export const a = (x: string) => import("./" + x);\n',
    "src/v1/lib/concatenatedLiterals.ts":
      'export const a = () => import("./" + "../../services/a");\n',
    // A prefix with no "/" fixes no folder: `.${n}` may become `../x`.
    "src/v1/lib/dotPrefix.ts":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n: string) => import(`.${n}`);\n",
    "src/v1/lib/aliasPrefix.ts":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (p: string) => import(`@v1${p}`);\n",
    "src/v1/lib/urlVariable.ts":
      "export const a = (p: string) => new URL(p, import.meta.url);\n",
    "src/v1/components/ui/globAnyFolder.ts":
      'export const a = import.meta.glob("@v1/*/a.ts");\n',
    "src/v1/lib/broken.ts": "export const = 1;\n",
    // A `base` that is not a string literal could point anywhere.
    "src/v1/lib/globBaseVariable.ts":
      'export const a = (b: string) => import.meta.glob("./*.ts", { base: b });\n',
    "src/v1/lib/globOptionsSpread.ts":
      'const o = { base: "../../x" };\nexport const a = import.meta.glob("./*.ts", { ...o });\n',
  };
  const reported = checkCode(files);
  const unanalysable = [
    "variable",
    "fullyComputed",
    "concatenation",
    "concatenatedLiterals",
    "dotPrefix",
    "aliasPrefix",
    "urlVariable",
    "globBaseVariable",
    "globOptionsSpread",
  ];
  for (const file of unanalysable) {
    const lines = linesFor(reported, `src/v1/lib/${file}.ts`);
    assert.equal(lines.length, 1, `${file}:\n${reported.join("\n")}`);
    assert.ok(lines[0].includes("unanalysable import"), lines[0]);
  }
  for (const file of ["computedPage", "globAnyFolder"]) {
    const lines = linesFor(reported, `src/v1/components/ui/${file}.ts`);
    assert.equal(lines.length, 1, `${file}:\n${reported.join("\n")}`);
    assert.ok(lines[0].includes("may not import a computed v1 path"), lines[0]);
  }
  const broken = linesFor(reported, "src/v1/lib/broken.ts");
  assert.equal(broken.length, 1, reported.join("\n"));
  assert.ok(broken[0].includes("could not parse"), broken[0]);
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
    "templateAsConst.tsx":
      "export const a = () => import(`@v1/plugins/manifest` as const);",
    "angleAssertion.ts":
      'export const a = () => import(<string>"@v1/plugins/manifest");',
    "nonNull.ts": 'export const a = () => import("@v1/lib/x"!);',
    "nestedWrappers.ts":
      'export const a = () => import(("@v1/lib/x" as const)!);',
    "globArrayAsConst.ts":
      'export const a = import.meta.glob(["@v1/lib/*.ts"] as const);',
    "globBase.jsx":
      'export const a = import.meta.glob("./*.ts", { base: "/src/v1/lib" });',
    "globClimbsLater.jsx":
      'export const a = import.meta.glob("./*/../../v1/lib/*.ts");',
    // Vite globs a concatenation on the string it starts with.
    "concatenation.jsx":
      'export const a = (n) => import("../v1/lib/" + n + ".ts");',
    "concatCall.jsx": 'export const a = (n) => import("../v1/lib/".concat(n));',
    "conditional.jsx":
      'export const a = (c) => import(c ? "../v1/lib/x" : "./b");',
    "aliasV0Unslashed.jsx":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n) => import(`@/v1${n}`);",
    "aliasUnslashed.jsx":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (p) => import(`@v1${p}`);",
    "globWildcard.jsx": 'export const a = import.meta.glob("../**/*.ts");',
    "escaped.jsx": 'export const a = () => import("..\\/v1/lib/x");',
    "afterJsxText.jsx":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      'export const P = ({ d, t, x }) => <p>{d}/{t} {String(`progress/${x}`)}</p>;\nexport const later = () => import("@/v1/lib/x");',
    "styles.css": '@import "../v1/styles/tokens.css";',
    "tailwindReference.css": '@reference "../v1/styles/tokens.css";',
    "stylesNoSpace.css": '@import"../v1/styles/tokens.css";',
    "stylesUpperCase.css": '@IMPORT "../v1/styles/tokens.css";',
    "stylesImageSet.css":
      '.a { background-image: image-set("../v1/assets/a.svg" 1x); }',
    "stylesEscapedUrl.css": ".a { background: url(\\.\\./v1/assets/a.svg); }",
    // Vite can load any file (`?worker`), so an unknown type is read as code.
    "worker.mod": 'import "../v1/lib/x";',
    "stylesRootAbsolute.css": ".a { background: url(/src/v1/styles/a.png); }",
  };
  const allowed = {
    "entry.jsx": 'import "@v1";',
    "entryTemplate.jsx": "export const a = () => import(`@v1`);",
    "entryIndex.jsx": 'import "@v1/index";',
    "v0Only.jsx": 'import x from "../helpers/x";\nexport const y = x;',
    "v0Template.jsx":
      // biome-ignore lint/suspicious/noTemplateCurlyInString: source text containing a template literal.
      "export const a = (n) => import(`../helpers/${n}`);",
    "memberImport.jsx": "export const a = (api, f) => api.import(f);",
    "concatV0.jsx": 'export const a = (n) => import("../helpers/" + n);',
    "variableV0.jsx": "export const a = (n) => import(n);",
    "globBaseV0.jsx":
      'export const a = import.meta.glob("./*.ts", { base: "../helpers" });',
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

test("v1 styles: imports and Tailwind directives follow the contract", () => {
  const denied = {
    "reference.css": ['@reference "../../index.css";', "is outside src/v1"],
    "plugin.css": ['@plugin "../../../plugins/x.js";', "is outside src/v1"],
    "config.css": [
      '@config "../../../tailwind.config.js";',
      "is outside src/v1",
    ],
    "intoPage.css": [
      '@import "@v1/pages/a/x.css";',
      "styles/ may not import from pages/a/",
    ],
    "climbs.css": ['@import "../styles/tokens.css";', "climbs with '../'"],
    // At-rules are case-insensitive and need no space before a string.
    "noSpace.css": ['@import"../../index.css";', "is outside src/v1"],
    "upperCase.css": ['@IMPORT "../../index.css";', "is outside src/v1"],
    // A `/*` inside a string is not a comment.
    "afterSlashStarInString.css": [
      '.a { content: "/*"; }\n.b { background: url("../../x.png"); }\n/* end */',
      "is outside src/v1",
    ],
    "broken.css": [".a {", "could not parse"],
    // Vite reads strings in image-set() and drops backslash escapes.
    "imageSet.css": [
      '.a { background-image: image-set("../../assets/a.png" 1x, "../../assets/b.png" 2x); }',
      "is outside src/v1",
      2,
    ],
    "webkitImageSetUrl.css": [
      '.a { background-image: -webkit-image-set(url("../../assets/a.png") 1x); }',
      "is outside src/v1",
    ],
    "escapedUrl.css": [
      '.a { background: url("\\.\\./\\.\\./assets/a.png"); }',
      "is outside src/v1",
    ],
    "importNoTarget.css": ["@import;", "unanalysable import"],
    "importUrl.css": ['@import url("../../index.css");', "is outside src/v1"],
  };
  const allowed = {
    "ok.css": [
      '@import "tailwindcss";',
      '@import "@v1/styles/tokens.css";',
      '@reference "./tokens.css";',
      '@plugin "tailwindcss-animate";',
      '.a { background: url("@v1/assets/a.png"); }',
      ".b { background: url(data:image/png;base64,AA); }",
      '.c { background-image: image-set("@v1/assets/a.png" 1x); }',
    ].join("\n"),
  };
  const files = {};
  for (const [name, [code]] of Object.entries(denied)) {
    files[`src/v1/styles/${name}`] = `${code}\n`;
  }
  for (const [name, code] of Object.entries(allowed)) {
    files[`src/v1/styles/${name}`] = `${code}\n`;
  }
  const reported = checkCode(files);
  for (const [name, [, message, count = 1]] of Object.entries(denied)) {
    const lines = linesFor(reported, `src/v1/styles/${name}`);
    assert.equal(lines.length, count, `${name}:\n${reported.join("\n")}`);
    for (const line of lines) {
      assert.ok(line.includes(message), `${name}: ${line}`);
    }
  }
  assert.deepEqual(linesFor(reported, "src/v1/styles/ok.css"), []);
});

test("v0 symlinks: a link into v1 is reported, a file link is scanned", () => {
  const dir = makeTree(null);
  try {
    writeFile(dir, "elsewhere/bad.jsx", 'import "@v1/lib/x";\n');
    fs.mkdirSync(path.join(dir, "src", "pages"), { recursive: true });
    fs.symlinkSync(
      path.join(dir, "src", "v1", "plugins", "manifest.ts"),
      path.join(dir, "src", "pages", "manifest.ts"),
    );
    fs.symlinkSync(
      path.join(dir, "elsewhere", "bad.jsx"),
      path.join(dir, "src", "pages", "bad.jsx"),
    );
    const { output, log } = runAll(dir, ["node scripts/check-v1.mjs --code"]);
    assert.ok(output.includes("src/pages/manifest.ts: links into src/v1"), log);
    assert.ok(output.includes("src/pages/bad.jsx:1: '@v1/lib/x' reaches"), log);
  } finally {
    removeTree(dir);
  }
});

test("v0 at the top of src/: a glob `base` is resolved from there", () => {
  const reported = checkCode({
    "src/RootGlob.jsx":
      'export const a = import.meta.glob("./*.ts", { base: "v1/lib" });\n',
  });
  const lines = linesFor(reported, "src/RootGlob.jsx");
  assert.equal(lines.length, 1, reported.join("\n"));
  assert.ok(lines[0].includes("reaches into src/v1"), lines[0]);
});

test("v1 --code reads unknown file types and style files outside styles/", () => {
  // Cloud CI runs only --code, so it must not rely on --files rejecting these.
  const reported = checkCode({
    "src/v1/lib/bridge.mod": 'import "../../store/alert.js";\n',
    "src/v1/components/ui/Badge.pcss":
      '@import "../../../index.css";\n.ant-btn { color: red; }\n',
  });
  const bridge = linesFor(reported, "src/v1/lib/bridge.mod");
  assert.equal(bridge.length, 1, reported.join("\n"));
  assert.ok(bridge[0].includes("is outside src/v1"), bridge[0]);
  const badge = linesFor(reported, "src/v1/components/ui/Badge.pcss");
  assert.equal(badge.length, 2, reported.join("\n"));
  assert.ok(badge[0].includes("is outside src/v1"), badge[0]);
  assert.ok(badge[1].includes("No antd 'ant-' class names"), badge[1]);
});
