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
 * Imports are read from the syntax tree (@babel/parser), so comments,
 * strings, regexes and JSX text never hide or fake one: static import/export
 * statements, `import x = require()`, `typeof import()` types, and the calls
 * Vite resolves: import(), require(), import.meta.glob() and
 * new URL(..., import.meta.url). A template or glob argument is checked by its
 * fixed prefix. In v1, an argument that is neither (a variable, a
 * concatenation, a prefix with no `/`) is reported as unanalysable rather
 * than passed, and so is a file that does not parse.
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
import { parse } from "@babel/parser";

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
// Specifiers that leave src/v1 by name: root-absolute, the v0 alias, src/.
const OUTSIDE = /^(\/|@\/|src\/)/;
// `./...` and `../...`, resolved against the importing file.
const RELATIVE = /^\.\.?(\/|$)/;
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
 * Parses a JS or TS file into a Babel AST: { ast }, or { error, line } when
 * it does not parse. `.ts` files get no JSX, so `<T>x` casts still parse.
 */
function parseCode(src, name) {
  const isTs = /\.(ts|tsx|mts|cts)$/.test(name);
  const plugins = isTs ? ["typescript"] : [];
  if (!isTs || name.endsWith(".tsx")) {
    plugins.push("jsx");
  }
  try {
    return { ast: parse(src, { sourceType: "module", plugins }) };
  } catch (err) {
    return { error: err.message, line: err.loc?.line ?? 0 };
  }
}

// Positions and attached comments, not child nodes.
const NOT_CHILDREN = new Set([
  "loc",
  "start",
  "end",
  "extra",
  "leadingComments",
  "trailingComments",
  "innerComments",
]);

/* Every node under root. */
function* nodes(root) {
  const stack = [root];
  while (stack.length > 0) {
    const node = stack.pop();
    yield node;
    for (const [key, value] of Object.entries(node)) {
      if (
        NOT_CHILDREN.has(key) ||
        value === null ||
        typeof value !== "object"
      ) {
        continue;
      }
      for (const child of Array.isArray(value) ? value : [value]) {
        if (typeof child?.type === "string") {
          stack.push(child);
        }
      }
    }
  }
}

/* Whether node is `import.meta.<prop>`. */
function isImportMeta(node, prop) {
  return (
    node?.type === "MemberExpression" &&
    !node.computed &&
    node.object.type === "MetaProperty" &&
    node.object.meta.name === "import" &&
    node.property.name === prop
  );
}

/*
 * An import argument: { kind: "literal", spec } for a plain string;
 * { kind: "prefix", spec } for a template with `${}` or a glob with a
 * wildcard, spec being the fixed part before the first one;
 * { kind: "opaque" } for anything else (a variable, a concatenation).
 */
function argOf(arg, isGlob) {
  let spec;
  let kind = "literal";
  if (arg?.type === "StringLiteral") {
    spec = arg.value;
  } else if (arg?.type === "TemplateLiteral") {
    // `cooked` is null only in tagged templates, which are not import calls.
    spec = arg.quasis[0].value.cooked;
    kind = arg.expressions.length > 0 ? "prefix" : "literal";
  } else {
    return { kind: "opaque" };
  }
  const wildcard = isGlob ? spec.search(/[*?{[]/) : -1;
  return wildcard === -1
    ? { kind, spec }
    : { kind: "prefix", spec: spec.slice(0, wildcard) };
}

/* Every import in the AST, as { kind, spec, index }, in source order. */
function importSpecs(ast) {
  const specs = [];
  const add = (arg, at, isGlob = false) =>
    specs.push({ ...argOf(arg, isGlob), index: at.start });
  for (const node of nodes(ast.program)) {
    switch (node.type) {
      case "ImportDeclaration":
      case "ExportAllDeclaration":
      case "ExportNamedDeclaration":
        if (node.source) {
          add(node.source, node);
        }
        break;
      case "TSImportEqualsDeclaration":
        if (node.moduleReference.type === "TSExternalModuleReference") {
          add(node.moduleReference.expression, node);
        }
        break;
      case "TSImportType":
        add(node.argument.literal ?? node.argument, node);
        break;
      case "ImportExpression":
        add(node.source, node);
        break;
      case "CallExpression":
        callSpecs(node, add);
        break;
      case "NewExpression":
        // Only `new URL(x, import.meta.url)` is a module reference.
        if (
          node.callee.type === "Identifier" &&
          node.callee.name === "URL" &&
          isImportMeta(node.arguments[1], "url")
        ) {
          add(node.arguments[0], node);
        }
        break;
      default:
        break;
    }
  }
  return specs.toSorted((a, b) => a.index - b.index);
}

/* import(), require() and import.meta.glob(); a method that happens to be
 * named `import` or `require` (`api.import(f)`) is not one of them. */
function callSpecs(node, add) {
  const { callee } = node;
  const [first] = node.arguments;
  if (
    callee.type === "Import" ||
    (callee.type === "Identifier" && callee.name === "require")
  ) {
    add(first, node);
  } else if (isImportMeta(callee, "glob")) {
    const patterns =
      first?.type === "ArrayExpression" ? first.elements : [first];
    for (const pattern of patterns) {
      // `!` patterns exclude files rather than import them.
      if (
        !(pattern?.type === "StringLiteral" && pattern.value.startsWith("!"))
      ) {
        add(pattern, pattern ?? node, true);
      }
    }
  }
}

/* The name a property key spells, or undefined when it is computed. */
function keyName(key, computed) {
  if (!computed && key.type === "Identifier") {
    return key.name;
  }
  return key.type === "StringLiteral" ? key.value : undefined;
}

function isPropTypes(node) {
  switch (node.type) {
    case "MemberExpression":
      return keyName(node.property, node.computed) === "propTypes";
    case "ObjectProperty":
    case "ClassProperty":
      return keyName(node.key, node.computed) === "propTypes";
    case "VariableDeclarator":
      return node.id.type === "Identifier" && node.id.name === "propTypes";
    default:
      return false;
  }
}

// The nodes that hold text, where a class name can appear.
const TEXT_NODES = new Set(["StringLiteral", "TemplateElement", "JSXText"]);

/* PropTypes and antd `ant-` class names, as { index, msg }. */
function* bannedUses(ast, src) {
  for (const node of nodes(ast.program)) {
    if (isPropTypes(node)) {
      yield {
        index: node.start,
        msg: "No PropTypes under v1; type props with TypeScript.",
      };
    }
    if (TEXT_NODES.has(node.type)) {
      // Also catches built names (`ant-${x}`, "ant-" + x).
      const text = src.slice(node.start, node.end);
      for (const m of text.matchAll(/(?<![\w$-])ant-/g)) {
        yield {
          index: node.start + m.index,
          msg: "No antd 'ant-' class names under v1.",
        };
      }
    }
  }
}

/* CSS has block comments only; a `//` there is part of a URL. */
function blankCssComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
}

// CSS `@import`, Tailwind's `@reference` / `@plugin` / `@config`, and `url()`.
const CSS_IMPORT_RE =
  /(?:@(?:import|reference|plugin|config)\s+(?:url\(\s*)?|url\(\s*)["']?([^"')\s;]+)/g;

/* A `@v1/` or relative specifier as a path relative to src/v1, or
 * "outside" when it leaves src/v1. */
function resolveV1(spec, fileRel) {
  const rel = spec.startsWith("@v1/")
    ? path.posix.normalize(spec.slice(4))
    : path.posix.join(path.posix.dirname(fileRel), spec);
  return rel === ".." || rel.startsWith("../") ? "outside" : rel;
}

const climbs = (spec) => spec.split("/").includes("..");

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
  if (!spec.startsWith("@v1/") && !RELATIVE.test(spec)) {
    return undefined;
  }
  const rel = resolveV1(spec, fileRel);
  if (rel === "outside") {
    return rel;
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
  const dir = prefix.slice(0, prefix.lastIndexOf("/") + 1);
  if (!dir.startsWith("@v1/") && !RELATIVE.test(dir)) {
    return undefined;
  }
  const rel = resolveV1(dir, fileRel);
  if (rel === "outside") {
    return rel;
  }
  const isRoot = rel === "" || rel === "." || rel === "./";
  return (isRoot ? null : folderOf(rel, true)) ?? "any";
}

/* The problem with one v1 import, or null. A prefix with no "/" fixes no
 * directory at all (`.${n}` may become `../x`, `@v1${n}` any folder). */
function v1ImportProblem(folder, rel, arg, isTestFile) {
  if (
    arg.kind === "opaque" ||
    (arg.kind === "prefix" && !arg.spec.includes("/"))
  ) {
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
  if (to !== null && to !== "any" && !mayImport(folder, to, isTestFile)) {
    return `${folder}/ may not import from ${to}/ ('${spec}'); see the folder contract in src/v1/README.md.`;
  }
  // A `..` that stays inside v1 is still not how v1 imports.
  if (climbs(spec)) {
    return `'${spec}' climbs with '../'; import with './' within a folder and '@v1/...' across folders.`;
  }
  if (to === null) {
    return `'${spec}' is outside the v1 folder taxonomy.`;
  }
  if (to === "any" && CONTRACT[contractKey(folder)] !== ALL) {
    return `${folder}/ may not import a computed v1 path ('${spec}...'); only app/, plugins/, test/ and the entry may.`;
  }
  return null;
}

/* The problem with one import in a styles/ file, or null. */
function cssImportProblem(spec, rel) {
  if (ANTD.test(spec)) {
    return "antd is not used under src/v1.";
  }
  if (targetFolder(spec, rel) === "outside") {
    return `'${spec}' is outside src/v1; v1 styles import nothing outside it.`;
  }
  return v1ImportProblem("styles", rel, { kind: "literal", spec }, false);
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
      const problem = cssImportProblem(m[1], rel);
      if (problem) {
        report(rel, lineAt(css, m.index), problem);
      }
    }
    for (const m of css.matchAll(/(?<![\w$-])ant-/g)) {
      report(rel, lineAt(css, m.index), "No antd 'ant-' class names under v1.");
    }
  }

  if (!runCode || !CODE_EXT.test(name) || folder === null) {
    continue;
  }
  const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
  const parsed = parseCode(src, name);
  if (parsed.error) {
    report(rel, parsed.line, `could not parse (${parsed.error}).`);
    continue;
  }
  const isTestFile = TEST_FILE.test(name);

  for (const arg of importSpecs(parsed.ast)) {
    const problem = v1ImportProblem(folder, rel, arg, isTestFile);
    if (problem) {
      report(rel, lineAt(src, arg.index), problem);
    }
  }
  for (const { index, msg } of bannedUses(parsed.ast, src)) {
    report(rel, lineAt(src, index), msg);
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
  if (spec.startsWith("@v1")) {
    return `src/v1${spec.slice(3)}`;
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
 * A template or glob can still add to its fixed prefix, so it reaches v1
 * when the prefix is inside v1 or could grow into it (`@/v1${n}`, `../**`). */
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
  const norm = path.posix.normalize(target).replace(/^\.\/?$/, "");
  if (norm === "src/v1" || norm.startsWith("src/v1/")) {
    return true;
  }
  return arg.kind === "prefix" && "src/v1/".startsWith(norm);
}

function v0Specs(rel, raw) {
  if (!STYLE_EXT.test(rel)) {
    const parsed = parseCode(raw, rel);
    return parsed.error
      ? { error: parsed }
      : { text: raw, specs: importSpecs(parsed.ast) };
  }
  const text = blankCssComments(raw);
  const specs = [...text.matchAll(CSS_IMPORT_RE)].map((m) => ({
    kind: "literal",
    spec: m[1],
    index: m.index,
  }));
  return { text, specs };
}

/* The real path of a symlink, or null when it is broken. */
function realPath(file) {
  try {
    return fs.realpathSync(file);
  } catch {
    return null;
  }
}

function checkV0() {
  const v1Real = fs.realpathSync(ROOT);
  for (const rel of walk(SRC)) {
    const full = path.join(SRC, rel);
    if (rel.startsWith("v1/")) {
      continue;
    }
    if (fs.lstatSync(full).isSymbolicLink()) {
      const real = realPath(full);
      if (real === v1Real || real?.startsWith(`${v1Real}${path.sep}`)) {
        problems.push(
          `src/${rel}: links into src/v1; v0 may reach v1 only through the '@v1' entry.`,
        );
        continue;
      }
      // A file link is scanned like the file; a folder link is not followed.
      if (real === null || !fs.statSync(real).isFile()) {
        continue;
      }
    }
    if (!STYLE_EXT.test(rel) && !V0_CODE_EXT.test(rel)) {
      continue;
    }
    const { text, specs, error } = v0Specs(rel, fs.readFileSync(full, "utf8"));
    if (error) {
      problems.push(
        `src/${rel}:${error.line}: could not parse (${error.error}).`,
      );
      continue;
    }
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
