#!/usr/bin/env node
/*
 * Guard for the v1 frontend (src/v1/): the rules Biome cannot express.
 *
 *   --files  TypeScript only (a .js under v1 is skipped by tsc, not failed,
 *            because allowJs is off), style files only in styles/, no file
 *            type outside an allowlist, no symlinks, and every file inside
 *            the v1 folder taxonomy. Run by `typecheck:v1`.
 *   --code   Imports: nothing outside src/v1 and the folder import contract
 *            (which v1 folder may import which). No PropTypes, no antd `ant-`
 *            class names, and one notification entry point: toast
 *            libraries only in components/ui/feedback/. Also scans v0 (the rest of src/) for imports that
 *            reach into v1 other than through `@v1`. Every file is read
 *            except assets, data and docs; one of unknown type is read as
 *            code, since Vite can load any file (`?worker`). Run by
 *            `lint:v1`.
 *
 * With neither flag, both run. It checks the src/ beside this script; the
 * fixtures in test-fixtures/v1-boundary/ copy it into each throwaway tree for
 * that reason.
 *
 * Imports are read from syntax trees (@babel/parser for code, PostCSS for
 * styles), so comments, strings, regexes and JSX text never hide or fake one:
 * static import/export statements, `import x = require()`, `typeof import()`
 * types, and the calls Vite resolves: import(), require(), import.meta.glob()
 * (with its `base` option) and new URL(..., import.meta.url). A template or
 * glob argument is checked by its fixed prefix, and a `..` after that prefix
 * is reported. In v1, an argument that is neither (a variable, a
 * concatenation, a prefix with no `/`) is reported as unanalysable rather
 * than passed, and so is a file that does not parse. v0 is judged by what
 * Vite can resolve: a concatenation by the string it starts with, as Vite
 * globs it; a bare variable is left alone, since Vite cannot bundle it.
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
import postcss from "postcss";
import valueParser from "postcss-value-parser";

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
// Vite's CSS languages (CSS_LANGS_RE); PostCSS reads them without a plugin
// only when they are plain CSS, and anything else fails to parse.
const STYLE_EXT = /\.(css|less|sass|scss|styl|stylus|pcss|postcss|sss)$/i;
// Vite's asset types (KNOWN_ASSET_TYPES), and data and docs: Vite resolves
// nothing inside them.
const INERT_EXT =
  /\.(apng|bmp|png|jpe?g|jfif|pjpeg|pjp|gif|svg|ico|webp|avif|cur|jxl|mp4|webm|ogg|mp3|wav|flac|aac|opus|mov|m4a|vtt|woff2?|eot|ttf|otf|webmanifest|pdf|txt|json|md)$/i;
const TEST_FILE = /\.(test|spec)\.(ts|tsx|mts|cts)$/;

/* How a file is read: "code", "style", "inert" (nothing in it is resolved
 * as an import) or "unknown", which is read as code. */
function fileKind(name) {
  if (CODE_EXT.test(name) || JS_EXT.test(name)) {
    return "code";
  }
  if (STYLE_EXT.test(name)) {
    return "style";
  }
  return INERT_EXT.test(name) || name === ".gitkeep" ? "inert" : "unknown";
}
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
  // `dts` allows what only a declaration file may hold (`const x: T;`).
  const dts = /\.d\.[mc]?ts$/.test(name);
  const plugins = isTs ? [["typescript", { dts }]] : [];
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

/* The child nodes of node. */
function* children(node) {
  for (const [key, value] of Object.entries(node)) {
    if (NOT_CHILDREN.has(key) || value === null || typeof value !== "object") {
      continue;
    }
    for (const child of Array.isArray(value) ? value : [value]) {
      if (typeof child?.type === "string") {
        yield child;
      }
    }
  }
}

/* Every node under root. */
function* nodes(root) {
  const stack = [root];
  while (stack.length > 0) {
    const node = stack.pop();
    yield node;
    stack.push(...children(node));
  }
}

/* Whether node is `import.meta.<prop>`, type-only wrappers aside
 * (`import.meta.url as string`, `(import.meta.glob as any)`). */
function isImportMeta(node, prop) {
  const member = unwrap(node);
  const object = unwrap(member?.object);
  return (
    member?.type === "MemberExpression" &&
    !member.computed &&
    object?.type === "MetaProperty" &&
    object.meta.name === "import" &&
    member.property.name === prop
  );
}

// Stands for a `${}` hole while a template is read as one string.
const HOLE = "\0";

/*
 * The import arguments node stands for (a conditional stands for both
 * branches), each as { kind, spec }: "literal" for a plain string; "prefix"
 * for a template with `${}` or a glob with a wildcard, spec being the fixed
 * part before the first one; "opaque" for anything else. Vite globs a
 * concatenation (`"./a/" + n`, `"./a/".concat(n)`) on the string it starts
 * with, so an opaque argument keeps that as `start`. `climbsLater` marks a
 * `..` segment after the prefix, which can leave the folder the prefix names.
 */
function argsOf(node, isGlob) {
  const arg = unwrap(node);
  if (arg?.type === "ConditionalExpression") {
    return [
      ...argsOf(arg.consequent, isGlob),
      ...argsOf(arg.alternate, isGlob),
    ];
  }
  const text = fixedText(arg);
  if (text === undefined) {
    return [{ kind: "opaque", start: concatStart(arg) }];
  }
  const at = text.search(isGlob ? /[*?{[\0]/ : /\0/);
  if (at === -1) {
    return [{ kind: "literal", spec: text }];
  }
  const climbsLater = text
    .slice(at)
    .split("/")
    .some((seg) => seg.replace(/[*?\0]/g, "") === "..");
  return [{ kind: "prefix", spec: text.slice(0, at), climbsLater }];
}

/* A string or template as text, holes as HOLE; undefined for anything else.
 * `cooked` is null only in tagged templates, which are not import calls. */
function fixedText(arg) {
  if (arg?.type === "StringLiteral") {
    return arg.value;
  }
  if (arg?.type === "TemplateLiteral") {
    return arg.quasis.map((q) => q.value.cooked).join(HOLE);
  }
  return undefined;
}

/* The fixed text a `+` chain or `.concat()` call starts with, if any. */
function concatStart(node) {
  const arg = unwrap(node);
  let first;
  if (arg?.type === "BinaryExpression" && arg.operator === "+") {
    first = arg.left;
  } else if (
    arg?.type === "CallExpression" &&
    arg.callee.type === "MemberExpression" &&
    keyName(arg.callee.property, arg.callee.computed) === "concat"
  ) {
    first = arg.callee.object;
  } else {
    return undefined;
  }
  const text = fixedText(unwrap(first));
  return text === undefined ? concatStart(first) : text.split(HOLE)[0];
}

// Type-only wrappers: `x as const`, `x satisfies T`, `<T>x`, `x!`.
// Parentheses leave no node of their own.
const WRAPPERS = new Set([
  "TSAsExpression",
  "TSSatisfiesExpression",
  "TSTypeAssertion",
  "TSNonNullExpression",
]);

/* The expression inside any type-only wrappers. */
function unwrap(node) {
  let inner = node;
  while (WRAPPERS.has(inner?.type)) {
    inner = inner.expression;
  }
  return inner;
}

/* Every import in the AST, as { kind, spec, line }, in source order. */
function importSpecs(ast) {
  const specs = [];
  const push = (args, at) => {
    for (const arg of args) {
      specs.push({ ...arg, line: at.loc.start.line, index: at.start });
    }
  };
  const add = (arg, at) => push(argsOf(arg, false), at);
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
        callSpecs(node, add, push);
        break;
      case "NewExpression":
        // Only `new URL(x, import.meta.url)` is a module reference.
        if (
          isUrlCallee(node.callee) &&
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

function isUrlCallee(callee) {
  const inner = unwrap(callee);
  return inner?.type === "Identifier" && inner.name === "URL";
}

/* import(), require() and import.meta.glob(); a method that happens to be
 * named `import` or `require` (`api.import(f)`) is not one of them. */
function callSpecs(node, add, push) {
  const callee = unwrap(node.callee);
  const [first, options] = node.arguments;
  if (
    callee.type === "Import" ||
    (callee.type === "Identifier" && callee.name === "require")
  ) {
    add(first, node);
  } else if (isImportMeta(callee, "glob")) {
    const list = unwrap(first);
    const patterns = list?.type === "ArrayExpression" ? list.elements : [first];
    const base = globBase(options);
    for (const pattern of patterns) {
      const literal = unwrap(pattern);
      // `!` patterns exclude files rather than import them.
      if (
        !(literal?.type === "StringLiteral" && literal.value.startsWith("!"))
      ) {
        const args = argsOf(pattern, true).map((arg) => rebase(arg, base));
        push(args, pattern ?? node);
      }
    }
  }
}

/*
 * The `base` option of an import.meta.glob() call, which Vite resolves
 * relative patterns against: undefined when there is none, the string, or
 * null when it cannot be read (then every pattern is opaque).
 */
function globBase(options) {
  const opts = unwrap(options);
  if (opts === undefined) {
    return undefined;
  }
  if (opts.type !== "ObjectExpression") {
    return null;
  }
  let base;
  for (const prop of opts.properties) {
    // A spread, a method or a computed key might be `base`.
    const key =
      prop.type === "ObjectProperty"
        ? keyName(prop.key, prop.computed)
        : undefined;
    if (key === undefined) {
      return null;
    }
    if (key === "base") {
      base = unwrap(prop.value);
    }
  }
  if (base === undefined) {
    return undefined;
  }
  return base.type === "StringLiteral" ? base.value : null;
}

/* A glob argument with `base` applied; it applies to relative patterns only. */
function rebase(arg, base) {
  if (base === null) {
    return { kind: "opaque" };
  }
  if (base === undefined || base === "" || arg.kind === "opaque") {
    return arg;
  }
  if (!RELATIVE.test(arg.spec)) {
    return arg;
  }
  let spec = path.posix.join(base, arg.spec);
  if (arg.spec.endsWith("/") && !spec.endsWith("/")) {
    spec += "/";
  }
  return { ...arg, spec: /^[./@]/.test(spec) ? spec : `./${spec}` };
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

// An antd class name, not the tail of one like `variant-x`.
const ANT_CLASS = /(?<![\w$-])ant-/g;

// The nodes that hold text, where a class name can appear.
const TEXT_NODES = new Set(["StringLiteral", "TemplateElement", "JSXText"]);

/*
 * One notification entry point (P1-T13): v1 tells the user something happened
 * only through `notify()` in lib/notify.ts, which the Toaster in
 * components/ui/feedback/ implements. A toast library anywhere else would be
 * a second entry point; v0 already ships sonner, so it is one import away.
 */
const NOTIFY_HOME = "components/ui/feedback/";
const TOAST_PACKAGES =
  /^(sonner|react-hot-toast|react-toastify|notistack|@radix-ui\/react-toast)(\/|$)/;
const NOTIFY_MSG =
  "One notification entry point in v1: call notify() or toast.* from @v1/lib/notify; toast libraries are imported only in components/ui/feedback/.";

/*
 * Toast-library imports outside the feedback folder, as { index, msg }.
 *
 * radix-ui bundles every primitive, Toast among them, and a namespace, default,
 * dynamic, required or re-exported binding can reach Toast in more spellings
 * than a walk can follow (`R.Toast`, `<R.Toast.Root>`, `R["Toast"]`, aliases,
 * `.then`). So the rule is structural, not a hunt for spellings: outside the
 * feedback folder radix-ui may be used only as a static named import that does
 * not name Toast, and every other reference to it is reported. (antd's
 * notification and message are already rejected by Biome's noRestrictedImports,
 * which lint:v1 runs first.)
 */
const RADIX = /^radix-ui(\/|$)/;
const isNamedRadixImport = (node) =>
  node.type === "ImportDeclaration" &&
  node.source.value === "radix-ui" &&
  node.specifiers.length > 0 &&
  node.specifiers.every(
    (spec) =>
      spec.type === "ImportSpecifier" &&
      (spec.imported.name ?? spec.imported.value) !== "Toast",
  );

function* notifyEntryPoints(ast, specs) {
  const allowed = new Set(
    ast.program.body.filter(isNamedRadixImport).map((node) => node.start),
  );
  for (const arg of specs) {
    const spec = arg.spec ?? "";
    if (
      TOAST_PACKAGES.test(spec) ||
      (RADIX.test(spec) && !allowed.has(arg.index))
    ) {
      yield { index: arg.index, msg: NOTIFY_MSG };
    }
  }
}

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
      for (const m of text.matchAll(ANT_CLASS)) {
        yield {
          index: node.start + m.index,
          msg: "No antd 'ant-' class names under v1.",
        };
      }
    }
  }
}

// CSS `@import` and Tailwind's `@reference` / `@plugin` / `@config`.
const CSS_IMPORT_RULES = new Set(["import", "reference", "plugin", "config"]);

// Vite drops a backslash before any non-word character (`\.\./x`).
const cssUnescape = (spec) => spec.replace(/\\(\W)/g, "$1");

/* The target of an import at-rule: its first string, word or url(). */
function cssImportTarget(params) {
  const first = valueParser(params).nodes.find((n) => n.type !== "space");
  if (first?.type === "function" && first.value.toLowerCase() === "url") {
    return first.nodes.find((n) => n.type !== "space")?.value;
  }
  return first?.type === "string" || first?.type === "word"
    ? first.value
    : undefined;
}

/* The asset references in a CSS value, as Vite reads them: each url(), and
 * each string inside image-set() or -webkit-image-set(). */
function cssValueTargets(value) {
  const targets = [];
  valueParser(value).walk((node) => {
    if (node.type !== "function") {
      return;
    }
    const name = node.value.toLowerCase();
    if (name === "url") {
      const arg = node.nodes.find((n) => n.type !== "space");
      if (arg) {
        targets.push(arg.value);
      }
    } else if (name.endsWith("image-set")) {
      for (const arg of node.nodes) {
        if (arg.type === "string") {
          targets.push(arg.value);
        }
      }
    }
  });
  return targets;
}

/* The text of a PostCSS node that can hold a URL or a class name. */
function cssText(node) {
  if (node.type === "rule") {
    return node.selector;
  }
  if (node.type === "atrule") {
    return node.params;
  }
  return node.type === "decl" ? node.value : "";
}

/* The import targets in one PostCSS node; undefined for an import at-rule
 * whose target cannot be read. */
function cssNodeTargets(node) {
  if (node.type === "atrule" && CSS_IMPORT_RULES.has(node.name.toLowerCase())) {
    return [cssImportTarget(node.params)];
  }
  return node.type === "rule" ? [] : cssValueTargets(cssText(node));
}

/*
 * A stylesheet read with PostCSS, so comments and strings are told apart:
 * { imports: [{ spec, line }], antLines }, or { error, line } when it does
 * not parse. At-rule names are case-insensitive, and a string may follow one
 * with no space (`@import"x"`). `spec` is undefined for an import at-rule
 * whose target cannot be read.
 */
function cssScan(src) {
  let root;
  try {
    root = postcss.parse(src);
  } catch (err) {
    return { error: err.reason ?? err.message, line: err.line ?? 0 };
  }
  const imports = [];
  const antLines = [];
  root.walk((node) => {
    const line = node.source?.start?.line ?? 0;
    for (const target of cssNodeTargets(node)) {
      imports.push({ spec: target && cssUnescape(target), line });
    }
    if (cssText(node).match(ANT_CLASS)) {
      antLines.push(line);
    }
  });
  return { imports, antLines };
}

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
  if (arg.climbsLater) {
    return `'${spec}...' has '..' after a wildcard or \`\${}\`, so it can leave the folder it names; import with './' within a folder and '@v1/...' across folders.`;
  }
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

/* The problem with one import in a v1 style file, or null. */
function cssImportProblem(spec, rel, folder) {
  if (spec === undefined) {
    return "unanalysable import; use a string or url() target.";
  }
  if (ANTD.test(spec)) {
    return "antd is not used under src/v1.";
  }
  if (targetFolder(spec, rel) === "outside") {
    return `'${spec}' is outside src/v1; v1 styles import nothing outside it.`;
  }
  return v1ImportProblem(folder, rel, { kind: "literal", spec }, false);
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

function checkV1Css(rel, folder) {
  const scan = cssScan(fs.readFileSync(path.join(ROOT, rel), "utf8"));
  if (scan.error) {
    report(rel, scan.line, `could not parse (${scan.error}).`);
    return;
  }
  for (const { spec, line } of scan.imports) {
    const problem = cssImportProblem(spec, rel, folder);
    if (problem) {
      report(rel, line, problem);
    }
  }
  for (const line of scan.antLines) {
    report(rel, line, "No antd 'ant-' class names under v1.");
  }
}

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

  const kind = fileKind(name);
  if (runFiles) {
    if (JS_EXT.test(name)) {
      report(rel, 0, "v1 is TypeScript only; use .ts or .tsx.");
    }
    if (kind === "style" && folder !== "styles") {
      report(rel, 0, "No component style files; only styles/ holds CSS.");
    }
    if (kind === "unknown") {
      report(
        rel,
        0,
        "Unknown file type under v1; it holds TypeScript, styles (in styles/), Vite assets, JSON and Markdown.",
      );
    }
    if (
      isRootFile
        ? !ROOT_FILES.has(name)
        : folder === null && name !== ".gitkeep"
    ) {
      report(rel, 0, "Outside the v1 folder taxonomy (see src/v1/README.md).");
    }
  }

  // Style files and unknown types are read wherever they are, so --code
  // alone still checks what --files would reject.
  if (!runCode || folder === null || kind === "inert") {
    continue;
  }
  if (kind === "style") {
    checkV1Css(rel, folder);
    continue;
  }
  const src = fs.readFileSync(path.join(ROOT, rel), "utf8");
  const parsed = parseCode(src, name);
  if (parsed.error) {
    report(rel, parsed.line, `could not parse (${parsed.error}).`);
    continue;
  }
  const isTestFile = TEST_FILE.test(name);

  const specs = importSpecs(parsed.ast);
  for (const arg of specs) {
    const problem = v1ImportProblem(folder, rel, arg, isTestFile);
    if (problem) {
      report(rel, arg.line, problem);
    }
  }
  if (!rel.startsWith(NOTIFY_HOME)) {
    for (const { index, msg } of notifyEntryPoints(parsed.ast, specs)) {
      report(rel, lineAt(src, index), msg);
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

/*
 * Whether a v0 import reaches into v1 other than through the `@v1` entry.
 * A template, glob or concatenation can still add to its fixed start, so it
 * reaches v1 when that is inside v1 or could grow into it (`@/v1${n}`,
 * `../**`), or when a `..` follows it.
 */
function intoV1(arg, fileRel) {
  const spec = arg.kind === "opaque" ? arg.start : arg.spec;
  if (spec === undefined) {
    return false;
  }
  if (arg.kind === "literal" && ENTRY_SPEC.test(spec)) {
    return false;
  }
  const target = v0Target(spec, fileRel);
  if (target === undefined) {
    return false;
  }
  const norm = path.posix.normalize(target).replace(/^\.\/?$/, "");
  if (norm === "src/v1" || norm.startsWith("src/v1/")) {
    return true;
  }
  return (
    arg.kind !== "literal" &&
    ("src/v1/".startsWith(norm) || arg.climbsLater === true)
  );
}

function v0Specs(rel, raw) {
  if (STYLE_EXT.test(rel)) {
    const scan = cssScan(raw);
    return scan.error
      ? { error: scan }
      : { specs: scan.imports.map((i) => ({ kind: "literal", ...i })) };
  }
  const parsed = parseCode(raw, rel);
  return parsed.error ? { error: parsed } : { specs: importSpecs(parsed.ast) };
}

/* The real path of a symlink, or null when it is broken. */
function realPath(file) {
  try {
    return fs.realpathSync(file);
  } catch {
    return null;
  }
}

/* Whether to scan a v0 symlink; one into v1 is reported instead. A file
 * link is scanned like the file; a folder link is not followed. */
function scanV0Link(rel, full, v1Real) {
  const real = realPath(full);
  if (real === v1Real || real?.startsWith(`${v1Real}${path.sep}`)) {
    problems.push(
      `src/${rel}: links into src/v1; v0 may reach v1 only through the '@v1' entry.`,
    );
    return false;
  }
  return real !== null && fs.statSync(real).isFile();
}

function checkV0File(rel, full) {
  const { specs, error } = v0Specs(rel, fs.readFileSync(full, "utf8"));
  if (error) {
    problems.push(
      `src/${rel}:${error.line}: could not parse (${error.error}).`,
    );
    return;
  }
  for (const arg of specs) {
    if (intoV1(arg, rel)) {
      const spec =
        arg.kind === "literal" ? arg.spec : `${arg.spec ?? arg.start}...`;
      problems.push(
        `src/${rel}:${arg.line}: '${spec}' reaches into src/v1; v0 may import only the v1 public entry, as '@v1'.`,
      );
    }
  }
}

function checkV0() {
  const v1Real = fs.realpathSync(ROOT);
  for (const rel of walk(SRC)) {
    const full = path.join(SRC, rel);
    const scanned = fileKind(path.posix.basename(rel)) !== "inert";
    if (rel.startsWith("v1/")) {
      continue;
    }
    if (fs.lstatSync(full).isSymbolicLink() && !scanV0Link(rel, full, v1Real)) {
      continue;
    }
    if (scanned) {
      checkV0File(rel, full);
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
