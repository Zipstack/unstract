#!/usr/bin/env node
/*
 * Guard for the v1 frontend (src/v1/): the rules Biome cannot express.
 *
 *   --files  TypeScript only (a .js under v1 is skipped by tsc, not failed,
 *            because allowJs is off), style files only in styles/, no
 *            symlinks, and every file inside the v1 folder taxonomy. Run by
 *            `typecheck:v1`.
 *   --code   Imports: nothing outside src/v1 and the folder import contract
 *            (which v1 folder may import which). No PropTypes, no antd `ant-`
 *            class names. Also scans v0 (the rest of src/) for imports that
 *            reach into v1 other than through `@v1`. Run by `lint:v1`.
 *
 * With neither flag, both run. It checks the src/ beside this script; the
 * fixtures in test-fixtures/v1-boundary/ copy it into each throwaway tree for
 * that reason.
 *
 * Imports are read from static import/export statements and from the calls
 * Vite resolves: import(), require(), import.meta.glob() and
 * new URL(..., import.meta.url). A template argument is checked by its fixed
 * prefix. In v1, an argument that is neither (a variable, say) is reported as
 * unanalysable rather than passed.
 *
 * The v0 <-> v1 boundary is also a Biome rule (biome.json `overrides`), so CI
 * and editors report the plain forms. Biome overrides replace rule options
 * rather than merge them, which is why the per-folder contract lives here and
 * not as one override per folder.
 *
 * The `ant-` check exists only while antd markup survives in v0; drop it
 * once the shadcn migration is complete.
 */
import fs from "node:fs";
import path from "node:path";

const SRC = path.join(import.meta.dirname, "..", "src");
const ROOT = path.join(SRC, "v1");
const args = new Set(process.argv.slice(2));
const runFiles = args.has("--files") || !args.has("--code");
const runCode = args.has("--code") || !args.has("--files");

const ALL = "*";
/*
 * Folder -> folders it may import from, besides itself. `entry` is
 * src/v1/index.ts. Pages may not import other pages, app/, test/ (except
 * from test files) or the entry.
 * Mirrors the table in src/v1/README.md; change both together.
 */
const CONTRACT = {
  entry: ALL,
  app: ALL,
  plugins: ALL,
  test: ALL,
  pages: [
    "components/ui",
    "components/patterns",
    "shell",
    "services",
    "stores",
    "hooks",
    "lib",
    "styles",
    "assets",
    "plugins",
  ],
  "components/ui": ["lib", "styles", "assets"],
  "components/patterns": [
    "components/ui",
    "lib",
    "services",
    "stores",
    "hooks",
    "assets",
  ],
  shell: [
    "components/ui",
    "components/patterns",
    "services",
    "stores",
    "hooks",
    "lib",
    "assets",
  ],
  services: ["lib"],
  stores: ["lib"],
  hooks: ["lib"],
  lib: [],
  styles: ["lib", "assets"],
  // Static files (icons, logos, images); a generated icon map may live here.
  assets: [],
};
const TOP_LEVEL = new Set([
  "app",
  "shell",
  "services",
  "stores",
  "hooks",
  "lib",
  "styles",
  "assets",
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
// The v1 public entry, in the spellings that resolve to src/v1/index.ts.
const ENTRY_SPEC = /^@v1(\/index(\.ts)?)?$/;
// antd packages, which v1 styles may not pull in either.
const ANTD = /^(antd|@ant-design)(\/|$)/;

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
 * strings, template literals (including `${}` expressions) and regex
 * literals, so a `/*` or `//` inside any of them does not swallow the code
 * after it. A regex literal is told from division by the token before it.
 */
function blankComments(src) {
  let out = "";
  // The same text with string, template and regex bodies blanked too, so
  // import statements and calls are found only in executable code.
  let code = "";
  let i = 0;
  // "`" = inside a template literal; "{" = inside a `${}` or a brace in one.
  const stack = [];
  while (i < src.length) {
    if (stack.at(-1) === "`") {
      const opensOrCloses =
        src[i] === "`" || (src[i] === "$" && src[i + 1] === "{");
      const end = i + templateStep(src, i, stack);
      const chunk = src.slice(i, end);
      out += chunk;
      code += opensOrCloses ? chunk : blank(chunk);
      i = end;
      continue;
    }
    const end = tokenEnd(src, i, out, stack);
    const token = src.slice(i, end);
    if (isComment(src, i)) {
      out += blank(token);
      code += blank(token);
    } else {
      out += token;
      // A string or regex literal keeps only its opening delimiter.
      const literal = /^["'/]/.test(token) && token.length > 1;
      code += literal ? token[0] + blank(token.slice(1)) : token;
    }
    i = end;
  }
  return { text: out, code };
}

const blank = (s) => s.replace(/[^\n]/g, " ");

/* CSS has block comments only; a `//` there is part of a URL. */
function blankCssComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
}

function isComment(src, i) {
  return src[i] === "/" && (src[i + 1] === "/" || src[i + 1] === "*");
}

/* Index just past the code token that starts at i. */
function tokenEnd(src, i, out, stack) {
  if (isComment(src, i)) {
    return commentEnd(src, i);
  }
  if (src[i] === '"' || src[i] === "'") {
    return stringEnd(src, i);
  }
  if (src[i] === "/" && regexMayStart(out)) {
    const end = regexEnd(src, i);
    if (end !== -1) {
      return end;
    }
  }
  codeStep(src[i], stack);
  return i + 1;
}

// A `/` after one of these (or a keyword below) starts a regex, not division.
// `<` is left out so JSX closing tags (`</div>`) stay code.
const REGEX_AFTER = new Set("(,=:[!&|?{};+-*%>~^");
const REGEX_KEYWORDS = new Set([
  "return",
  "typeof",
  "case",
  "do",
  "else",
  "in",
  "of",
  "void",
  "yield",
  "await",
  "delete",
  "new",
]);

function regexMayStart(out) {
  const before = out.trimEnd();
  if (before === "") {
    return true;
  }
  const last = before.at(-1);
  if (REGEX_AFTER.has(last)) {
    return true;
  }
  const word = /[\w$]+$/.exec(before);
  return word !== null && REGEX_KEYWORDS.has(word[0]);
}

/* Index just past the regex literal at i, or -1 if it does not close on its
 * line (then it was division after all). */
function regexEnd(src, i) {
  let inClass = false;
  for (let j = i + 1; j < src.length; j += 1) {
    const c = src[j];
    if (c === "\n") {
      return -1;
    }
    if (c === "\\") {
      j += 1;
    } else if (c === "[") {
      inClass = true;
    } else if (c === "]") {
      inClass = false;
    } else if (c === "/" && !inClass) {
      return j + 1 + (/^[a-z]*/i.exec(src.slice(j + 1))?.[0].length ?? 0);
    }
  }
  return -1;
}

/* Index just past the line or block comment that starts at i. */
function commentEnd(src, i) {
  if (src[i + 1] === "/") {
    const newline = src.indexOf("\n", i);
    return newline === -1 ? src.length : newline;
  }
  const close = src.indexOf("*/", i + 2);
  return close === -1 ? src.length : close + 2;
}

/* Index just past the '...' or "..." string that starts at i. An unclosed
 * string ends at the newline. */
function stringEnd(src, i) {
  let j = i + 1;
  while (j < src.length && src[j] !== src[i] && src[j] !== "\n") {
    j += src[j] === "\\" ? 2 : 1;
  }
  return j + 1;
}

/* One step inside a template literal: how many characters to copy. Closing
 * the literal or opening `${` updates the stack. */
function templateStep(src, i, stack) {
  if (src[i] === "\\") {
    return 2;
  }
  if (src[i] === "`") {
    stack.pop();
    return 1;
  }
  if (src[i] === "$" && src[i + 1] === "{") {
    stack.push("{");
    return 2;
  }
  return 1;
}

/* Tracks template literals and the braces inside their `${}` expressions. */
function codeStep(c, stack) {
  if (c === "`") {
    stack.push("`");
  } else if (c === "{" && stack.length > 0) {
    stack.push("{");
  } else if (c === "}" && stack.length > 0) {
    stack.pop();
  }
}

// Static import/export statements, up to the quote of their string literal.
const STATIC_RE =
  /\b(?:import|export)\s+(?:type\s+)?(?:[\w$*{}\s,]+?\s+from\s+)?(?=["'])/g;
// Calls whose first argument Vite resolves as a module or asset.
const CALL_RE =
  /\b(import\.meta\.glob|import|require|new\s+URL)\s*(?:<[^>]*>)?\(\s*/g;
// CSS `@import` and `url()` targets.
const CSS_IMPORT_RE = /(?:@import\s+(?:url\(\s*)?|url\(\s*)["']?([^"')\s;]+)/g;

/*
 * The argument at j: { kind: "literal", spec } for a plain string;
 * { kind: "prefix", spec } for a template with `${}`, spec being the fixed
 * part before it; { kind: "opaque" } for anything else. `end` is the index
 * just past a string argument.
 */
function readArg(text, j) {
  const quote = text[j];
  if (quote !== '"' && quote !== "'" && quote !== "`") {
    return { kind: "opaque" };
  }
  const end = text.indexOf(quote, j + 1);
  if (end === -1) {
    return { kind: "opaque" };
  }
  const body = text.slice(j + 1, end);
  const hole = quote === "`" ? body.indexOf("${") : -1;
  return hole === -1
    ? { kind: "literal", spec: body, end: end + 1 }
    : { kind: "prefix", spec: body.slice(0, hole), end: end + 1 };
}

/*
 * Every import, as { kind, spec, index }. Statements and calls are found in
 * `code` (no string contents), and their argument is read from `text` at the
 * same offset.
 */
function* importSpecs({ text, code }) {
  for (const m of code.matchAll(STATIC_RE)) {
    const arg = readArg(text, m.index + m[0].length);
    if (arg.kind === "literal") {
      yield { ...arg, index: m.index };
    }
  }
  for (const m of code.matchAll(CALL_RE)) {
    yield* callSpecs(text, m);
  }
}

function* callSpecs(text, m) {
  const j = m.index + m[0].length;
  if (m[1] === "import.meta.glob" && text[j] === "[") {
    yield* globArraySpecs(text, j + 1);
    return;
  }
  const arg = readArg(text, j);
  if (m[1].startsWith("new")) {
    // Only `new URL(x, import.meta.url)` is a module reference.
    const base = arg.end === undefined ? "" : text.slice(arg.end, arg.end + 40);
    if (!/^\s*,\s*import\.meta\.url\b/.test(base)) {
      return;
    }
  }
  yield { ...arg, index: m.index };
}

/* Every pattern of an `import.meta.glob([...])` array; `!` patterns exclude
 * files rather than import them, so they are skipped. */
function* globArraySpecs(text, j) {
  let k = j;
  while (k < text.length) {
    k += /^[\s,]*/.exec(text.slice(k))[0].length;
    if (text[k] === "]") {
      return;
    }
    const arg = readArg(text, k);
    if (arg.kind !== "literal" || !arg.spec.startsWith("!")) {
      yield { ...arg, index: k };
    }
    if (arg.end === undefined) {
      return;
    }
    k = arg.end;
  }
}

/*
 * Classifies a specifier: "outside" when it leaves src/v1; the v1 folder it
 * names; null for a v1 path outside the taxonomy; undefined for a package.
 */
function targetFolder(spec, fileRel) {
  if (OUTSIDE.test(spec)) {
    return "outside";
  }
  if (ENTRY_SPEC.test(spec)) {
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
  return folderOf(rel, isDir) ?? folderOf(rel);
}

/*
 * Classifies a template's fixed prefix like targetFolder, by the directory it
 * fixes (up to its last "/"). "any" when that leaves the v1 folder open, as in
 * `@v1/pages/${name}`; only folders that may import everything may do that.
 */
function prefixFolder(prefix, fileRel) {
  if (OUTSIDE.test(prefix)) {
    return "outside";
  }
  if (!prefix.startsWith("@v1") && !prefix.startsWith("./")) {
    return undefined;
  }
  const dir = prefix.slice(0, prefix.lastIndexOf("/") + 1);
  const rel = dir.startsWith("@v1/")
    ? path.posix.normalize(dir.slice(4))
    : path.posix.join(path.posix.dirname(fileRel), dir);
  if (rel.startsWith("..")) {
    return "outside";
  }
  const isRoot = rel === "" || rel === "." || rel === "./";
  return (isRoot ? null : folderOf(rel, true)) ?? "any";
}

/* The problem with one v1 import, or null. */
function v1ImportProblem(folder, rel, arg, isTestFile) {
  if (arg.kind === "opaque" || (arg.kind === "prefix" && arg.spec === "")) {
    return "unanalysable import; use a string literal, or a template whose fixed prefix names the folder.";
  }
  const { spec } = arg;
  const to =
    arg.kind === "prefix" ? prefixFolder(spec, rel) : targetFolder(spec, rel);
  if (to === undefined) {
    return null;
  }
  if (to === "outside") {
    return `'${spec}' is outside src/v1; v1 imports nothing outside it.`;
  }
  if (to === null) {
    return `'${spec}' is outside the v1 folder taxonomy.`;
  }
  if (to === "any") {
    return CONTRACT[contractKey(folder)] === ALL
      ? null
      : `${folder}/ may not import a computed v1 path ('${spec}...'); only app/, plugins/, test/ and the entry may.`;
  }
  return mayImport(folder, to, isTestFile)
    ? null
    : `${folder}/ may not import from ${to}/ ('${spec}'); see the folder contract in src/v1/README.md.`;
}

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

// Finder litter; never committed (.gitignore), so not worth reporting.
const IGNORED = new Set([".DS_Store"]);

/* Every file under dir, plus symlinks, which are listed rather than
 * followed; callers decide what to do with them. */
function walk(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((d) => (d.isFile() || d.isSymbolicLink()) && !IGNORED.has(d.name))
    .map((d) =>
      path
        .relative(dir, path.join(d.parentPath, d.name))
        .replaceAll(path.sep, "/"),
    )
    .toSorted((a, b) => a.localeCompare(b));
}

const problems = [];
const report = (rel, line, msg) => {
  const where = line ? `${rel}:${line}` : rel;
  problems.push(`src/v1/${where}: ${msg}`);
};

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
    const css = blankCssComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
    for (const m of css.matchAll(CSS_IMPORT_RE)) {
      if (ANTD.test(m[1])) {
        report(rel, lineAt(css, m.index), "antd is not used under src/v1.");
      } else if (targetFolder(m[1], rel) === "outside") {
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
  const scanned = blankComments(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  const { text } = scanned;
  const isTestFile = TEST_FILE.test(name);

  for (const arg of importSpecs(scanned)) {
    const problem = v1ImportProblem(folder, rel, arg, isTestFile);
    if (problem) {
      report(rel, lineAt(text, arg.index), problem);
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

/*
 * The v0 -> v1 half: v0 (everything in src/ outside v1, including the cloud
 * src/plugins/ overlay) reaches v1 only through the `@v1` entry.
 */
const V0_CODE_EXT = /\.(js|jsx|mjs|cjs|ts|tsx|mts|cts)$/;

/* A v0 specifier as a path from the project root, or undefined for a
 * package. fileRel is relative to src/. */
function v0Target(spec, fileRel) {
  if (spec.startsWith("@v1/")) {
    return `src/v1/${spec.slice(4)}`;
  }
  if (spec.startsWith("@/")) {
    return `src/${spec.slice(2)}`;
  }
  if (spec.startsWith("/")) {
    return spec.slice(1);
  }
  if (spec.startsWith("src/")) {
    return spec;
  }
  if (spec.startsWith(".")) {
    return path.posix.join("src", path.posix.dirname(fileRel), spec);
  }
  return undefined;
}

/* Whether a v0 import reaches into v1 other than through the `@v1` entry.
 * A template is judged by the directory its fixed prefix names. */
function intoV1(arg, fileRel) {
  if (arg.kind === "opaque") {
    return false;
  }
  if (arg.kind === "literal" && ENTRY_SPEC.test(arg.spec)) {
    return false;
  }
  const target = v0Target(arg.spec, fileRel);
  if (target === undefined) {
    return false;
  }
  const norm = path.posix.normalize(target);
  const fixed =
    arg.kind === "prefix" ? norm.slice(0, norm.lastIndexOf("/") + 1) : norm;
  return fixed === "src/v1" || fixed.startsWith("src/v1/");
}

function v0Specs(rel, raw) {
  if (!STYLE_EXT.test(rel)) {
    const scanned = blankComments(raw);
    return { text: scanned.text, specs: importSpecs(scanned) };
  }
  const text = blankCssComments(raw);
  const specs = [...text.matchAll(CSS_IMPORT_RE)].map((m) => ({
    kind: "literal",
    spec: m[1],
    index: m.index,
  }));
  return { text, specs };
}

function checkV0() {
  for (const rel of walk(SRC)) {
    const full = path.join(SRC, rel);
    const inV1 = rel.startsWith("v1/");
    const scanned = STYLE_EXT.test(rel) || V0_CODE_EXT.test(rel);
    if (inV1 || !scanned || fs.lstatSync(full).isSymbolicLink()) {
      continue;
    }
    const { text, specs } = v0Specs(rel, fs.readFileSync(full, "utf8"));
    for (const arg of specs) {
      if (intoV1(arg, rel)) {
        problems.push(
          `src/${rel}:${lineAt(text, arg.index)}: '${arg.spec}' reaches into src/v1; v0 may import only the v1 public entry, as '@v1'.`,
        );
      }
    }
  }
}

if (runCode) {
  checkV0();
}

if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(`\ncheck-v1: ${problems.length} problem(s).`);
  process.exit(1);
}
console.log("check-v1: ok");
