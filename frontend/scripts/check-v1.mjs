#!/usr/bin/env node
/*
 * Guard for the v1 frontend (src/v1/): the rules Biome cannot express.
 *
 *   --files  TypeScript only (a .js under v1 is skipped by tsc, not failed,
 *            because allowJs is off), style files only in styles/, and every
 *            file inside the v1 folder taxonomy. Run by `typecheck:v1`.
 *   --code   The folder import contract (which v1 folder may import which),
 *            no PropTypes, no antd `ant-` class prefix. Run by `lint:v1`.
 *
 * With neither flag, both run. `--root <dir>` points it at another tree
 * (used by the fixtures in test-fixtures/v1-boundary/).
 *
 * The v0 <-> v1 boundary itself, `../` imports and banned packages are Biome
 * rules (biome.json `overrides`), so they also run in CI and in editors.
 * Biome overrides replace rule options rather than merge them, which is why
 * the per-folder contract lives here and not as one override per folder.
 *
 * The `ant-` check exists only while antd markup survives in v0; drop it
 * once the shadcn migration is complete.
 */
import fs from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const rootArg = args.indexOf("--root");
const ROOT = path.resolve(
  rootArg === -1
    ? path.join(import.meta.dirname, "..", "src", "v1")
    : args[rootArg + 1],
);
const runFiles = args.includes("--files") || !args.includes("--code");
const runCode = args.includes("--code") || !args.includes("--files");

const ALL = "*";
/*
 * Folder -> folders it may import from, besides itself. Mirrors the contract
 * table in the P0-T01 spec and src/v1/README.md. `entry` is src/v1/index.ts.
 * Pages may import everything except other pages.
 */
const CONTRACT = {
  entry: ALL,
  app: ALL,
  plugins: ALL,
  test: ALL,
  pages: ALL,
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
const TOP_LEVEL = new Set([
  "app",
  "shell",
  "services",
  "stores",
  "hooks",
  "lib",
  "styles",
  "plugins",
  "test",
]);
const ROOT_FILES = new Set(["index.ts", "tsconfig.json", "README.md"]);

const CODE_EXT = /\.(ts|tsx|mts|cts)$/;
const JS_EXT = /\.(js|jsx|mjs|cjs)$/;
const STYLE_EXT = /\.(css|scss|sass|less)$/;
const TEST_FILE = /\.(test|spec)\.tsx?$/;

/*
 * The v1 folder a path (relative to ROOT, `/`-separated) belongs to, e.g.
 * "components/ui" or "pages/settings"; null when it is outside the taxonomy.
 * `isDir` is for import targets like "@v1/lib", which name a folder.
 */
function folderOf(rel, isDir = false) {
  const segs = rel.split("/").filter(Boolean);
  const depth = isDir ? segs.length + 1 : segs.length;
  if (segs.length === 0 || (depth === 1 && segs[0] === "index.ts")) {
    return "entry";
  }
  if (depth === 1) {
    return null;
  }
  const [top, sub] = segs;
  if (top === "components") {
    return (sub === "ui" || sub === "patterns") && depth >= 3
      ? `components/${sub}`
      : null;
  }
  if (top === "pages") {
    return sub && depth >= 3 ? `pages/${sub}` : null;
  }
  return TOP_LEVEL.has(top) ? top : null;
}

function contractKey(folder) {
  return folder.startsWith("pages/") ? "pages" : folder;
}

function mayImport(from, to, isTestFile) {
  if (from === to) {
    return true;
  }
  if (isTestFile && to === "test") {
    return true;
  }
  if (from.startsWith("pages/") && to.startsWith("pages/")) {
    return false;
  }
  const allowed = CONTRACT[contractKey(from)];
  return allowed === ALL || allowed.includes(to);
}

/* Blanks comments while keeping line numbers, so matches can be reported. */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const IMPORT_RES = [
  /\b(?:import|export)\s+(?:type\s+)?(?:[\w$*{}\s,]+?\s+from\s+)?["']([^"']+)["']/g,
  /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
  /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
];

/* Resolves a specifier to a v1 folder, or undefined for packages and the
 * forms Biome already rejects (`../`, `@/`). */
function targetFolder(spec, fileRel) {
  if (spec === "@v1" || /^@v1\/index(\.ts)?$/.test(spec)) {
    return "entry";
  }
  let rel;
  if (spec.startsWith("@v1/")) {
    rel = path.posix.normalize(spec.slice(4));
  } else if (spec.startsWith("./")) {
    rel = path.posix.join(path.posix.dirname(fileRel), spec);
  } else {
    return undefined;
  }
  // No extension on the last segment -> it may name a folder ("@v1/lib").
  const isDir = !path.posix.extname(rel);
  return folderOf(rel, isDir) ?? folderOf(rel) ?? null;
}

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

function walk(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((d) => d.isFile())
    .map((d) =>
      path
        .relative(ROOT, path.join(d.parentPath, d.name))
        .replaceAll(path.sep, "/"),
    )
    .sort();
}

const problems = [];
const report = (rel, line, msg) =>
  problems.push(`src/v1/${rel}${line ? `:${line}` : ""}: ${msg}`);

if (!fs.existsSync(ROOT)) {
  console.error(`check-v1: ${ROOT} does not exist`);
  process.exit(2);
}

for (const rel of walk(ROOT)) {
  const name = path.posix.basename(rel);
  const isRootFile = !rel.includes("/");
  const folder = folderOf(rel);

  if (runFiles) {
    if (JS_EXT.test(name)) {
      report(rel, 0, "v1 is TypeScript only; use .ts or .tsx.");
    }
    if (STYLE_EXT.test(name) && folder !== "styles") {
      report(rel, 0, "No component style files; only styles/ holds CSS.");
    }
    if (
      isRootFile
        ? !ROOT_FILES.has(name)
        : folder === null && name !== ".gitkeep"
    ) {
      report(rel, 0, "Outside the v1 folder taxonomy (see src/v1/README.md).");
    }
  }

  if (!runCode || !CODE_EXT.test(name) || folder === null) {
    continue;
  }
  const text = stripComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  const isTestFile = TEST_FILE.test(name);

  for (const re of IMPORT_RES) {
    for (const m of text.matchAll(re)) {
      const to = targetFolder(m[1], rel);
      if (to === undefined) {
        continue;
      }
      if (to === null) {
        report(
          rel,
          lineAt(text, m.index),
          `'${m[1]}' is outside the v1 folder taxonomy.`,
        );
      } else if (!mayImport(folder, to, isTestFile)) {
        report(
          rel,
          lineAt(text, m.index),
          `${folder}/ may not import from ${to}/ ('${m[1]}'); see the folder contract in src/v1/README.md.`,
        );
      }
    }
  }
  for (const m of text.matchAll(/\.propTypes\b|\bpropTypes\s*[:=]/g)) {
    report(
      rel,
      lineAt(text, m.index),
      "No PropTypes under v1; type props with TypeScript.",
    );
  }
  for (const m of text.matchAll(/(?<![\w$-])ant-[a-z]/g)) {
    report(rel, lineAt(text, m.index), "No antd 'ant-' class names under v1.");
  }
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(`\ncheck-v1: ${problems.length} problem(s).`);
  process.exit(1);
}
console.log("check-v1: ok");
