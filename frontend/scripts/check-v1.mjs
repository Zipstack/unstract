#!/usr/bin/env node
/*
 * Guard for the v1 frontend (src/v1/): the rules Biome cannot express.
 *
 *   --files  TypeScript only (a .js under v1 is skipped by tsc, not failed,
 *            because allowJs is off), style files only in styles/, and every
 *            file inside the v1 folder taxonomy. Run by `typecheck:v1`.
 *   --code   Imports: nothing outside src/v1 and the folder import contract
 *            (which v1 folder may import which). No PropTypes, no antd `ant-`
 *            class names. Run by `lint:v1`.
 *
 * With neither flag, both run. It always checks the src/v1 beside this
 * script; the fixtures in test-fixtures/v1-boundary/ copy it into each
 * throwaway tree for that reason.
 *
 * The v0 <-> v1 boundary is also a Biome rule (biome.json `overrides`), so CI
 * and editors report it. The script repeats the v1 -> outside half because it
 * also reads template-literal imports, which Biome does not. Biome overrides
 * replace rule options rather than merge them, which is why the per-folder
 * contract lives here and not as one override per folder.
 *
 * The `ant-` check exists only while antd markup survives in v0; drop it
 * once the shadcn migration is complete.
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.join(import.meta.dirname, "..", "src", "v1");
const args = process.argv.slice(2);
const runFiles = args.includes("--files") || !args.includes("--code");
const runCode = args.includes("--code") || !args.includes("--files");

const ALL = "*";
/*
 * Folder -> folders it may import from, besides itself. `entry` is
 * src/v1/index.ts. Pages may import everything except other pages.
 * Mirrors the table in src/v1/README.md; change both together.
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
const TEST_FILE = /\.(test|spec)\.(ts|tsx|mts|cts)$/;
// Specifiers that leave src/v1: root-absolute, parent, the v0 alias, src/.
const OUTSIDE = /^(\/|\.\.(\/|$)|@\/|src\/)/;

/*
 * The v1 folder a path (relative to src/v1, `/`-separated) belongs to, e.g.
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

/*
 * Blanks comments, keeping line numbers so matches can be reported. Tracks
 * strings and template literals (including `${}` expressions), so a `/*` or
 * `//` inside a string does not swallow the code after it. Regex literals are
 * not tracked; a quote inside one is read as a string to the end of the line
 * at most, so it can hide that line only.
 */
function blankComments(src) {
  let out = "";
  let i = 0;
  // "`" = inside a template literal; "{" = inside a `${}` or a brace in one.
  const stack = [];
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (stack.at(-1) === "`") {
      if (c === "\\") {
        out += src.slice(i, i + 2);
        i += 2;
      } else if (c === "`") {
        stack.pop();
        out += c;
        i += 1;
      } else if (c === "$" && next === "{") {
        stack.push("{");
        out += "${";
        i += 2;
      } else {
        out += c;
        i += 1;
      }
      continue;
    }
    if (c === "/" && (next === "/" || next === "*")) {
      const close =
        next === "/" ? src.indexOf("\n", i) : src.indexOf("*/", i + 2);
      const end = close === -1 ? src.length : next === "/" ? close : close + 2;
      out += src.slice(i, end).replace(/[^\n]/g, " ");
      i = end;
    } else if (c === '"' || c === "'") {
      let j = i + 1;
      while (j < src.length && src[j] !== c && src[j] !== "\n") {
        j += src[j] === "\\" ? 2 : 1;
      }
      out += src.slice(i, j + 1);
      i = j + 1;
    } else {
      if (c === "`") {
        stack.push("`");
      } else if (c === "{" && stack.length > 0) {
        stack.push("{");
      } else if (c === "}" && stack.length > 0) {
        stack.pop();
      }
      out += c;
      i += 1;
    }
  }
  return out;
}

// A specifier: a quoted or backtick string with no interpolation.
const SPEC = "[\"'`]([^\"'`$]+)[\"'`]";
const IMPORT_RES = [
  new RegExp(
    `\\b(?:import|export)\\s+(?:type\\s+)?(?:[\\w$*{}\\s,]+?\\s+from\\s+)?${SPEC}`,
    "g",
  ),
  new RegExp(`\\bimport\\s*\\(\\s*${SPEC}\\s*[,)]`, "g"),
  new RegExp(`\\brequire\\s*\\(\\s*${SPEC}\\s*\\)`, "g"),
  // Vite globs; the first pattern of an array is checked.
  new RegExp(
    `\\bimport\\.meta\\.glob\\s*(?:<[^>]*>)?\\(\\s*\\[?\\s*${SPEC}`,
    "g",
  ),
];
// CSS `@import` and `url()` targets, for the files in styles/.
const CSS_IMPORT_RE = /(?:@import\s+(?:url\(\s*)?|url\(\s*)["']?([^"')\s;]+)/g;

/*
 * Classifies a specifier: "outside" when it leaves src/v1; the v1 folder it
 * names; null for a v1 path outside the taxonomy; undefined for a package.
 */
function targetFolder(spec, fileRel) {
  if (OUTSIDE.test(spec)) {
    return "outside";
  }
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
  if (rel.startsWith("..")) {
    return "outside";
  }
  // No extension on the last segment -> it may name a folder ("@v1/lib").
  const isDir = !path.posix.extname(rel);
  return folderOf(rel, isDir) ?? folderOf(rel) ?? null;
}

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

// Finder litter; never committed (.gitignore), so not worth reporting.
const IGNORED = new Set([".DS_Store"]);

/* Every file under dir, plus symlinks, which are reported rather than
 * followed: a linked file would bring outside code in unchecked. */
function walk(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((d) => (d.isFile() || d.isSymbolicLink()) && !IGNORED.has(d.name))
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

  if (fs.lstatSync(path.join(ROOT, rel)).isSymbolicLink()) {
    if (runFiles) {
      report(rel, 0, "No symlinks under v1; they bypass these checks.");
    }
    continue;
  }

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

  if (runCode && STYLE_EXT.test(name) && folder === "styles") {
    const css = blankComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
    for (const m of css.matchAll(CSS_IMPORT_RE)) {
      if (targetFolder(m[1], rel) === "outside") {
        report(
          rel,
          lineAt(css, m.index),
          `'${m[1]}' is outside src/v1; v1 styles import nothing outside it.`,
        );
      }
    }
    for (const m of css.matchAll(/(?<![\w$-])ant-/g)) {
      report(rel, lineAt(css, m.index), "No antd 'ant-' class names under v1.");
    }
  }

  if (!runCode || !CODE_EXT.test(name) || folder === null) {
    continue;
  }
  const text = blankComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  const isTestFile = TEST_FILE.test(name);

  for (const re of IMPORT_RES) {
    for (const m of text.matchAll(re)) {
      const to = targetFolder(m[1], rel);
      const line = lineAt(text, m.index);
      if (to === undefined) {
        continue;
      }
      if (to === "outside") {
        report(
          rel,
          line,
          `'${m[1]}' is outside src/v1; v1 imports nothing outside it.`,
        );
      } else if (to === null) {
        report(rel, line, `'${m[1]}' is outside the v1 folder taxonomy.`);
      } else if (!mayImport(folder, to, isTestFile)) {
        report(
          rel,
          line,
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
  // Also catches built names (`ant-${x}`, "ant-" + x).
  for (const m of text.matchAll(/(?<![\w$-])ant-/g)) {
    report(rel, lineAt(text, m.index), "No antd 'ant-' class names under v1.");
  }
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(`\ncheck-v1: ${problems.length} problem(s).`);
  process.exit(1);
}
console.log("check-v1: ok");
