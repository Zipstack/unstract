#!/usr/bin/env node
/*
 * Icon guard for the v1 frontend (src/v1/). Run by `lint:v1`.
 *
 *   1. Lucide is the only icon library. A package import is rejected, unless
 *      it is `lucide-react`, when its name contains `icon` or `lucide`
 *      (`@iconify/react`, `lucide-static`, `flag-icons`) or it is one of the
 *      known sets whose name does not say so (KNOWN_ICON_PACKAGES and
 *      KNOWN_ICON_SCOPES). The rule goes by package name, so an icon set
 *      outside both is not caught.
 *   2. Only canonical Lucide names. The deprecated aliases are read from the
 *      installed lucide-react's own export list, so they follow upgrades:
 *      `X as Y` is an alias unless Y is X, `XIcon` or `LucideX`.
 *   3. Only named imports from `lucide-react` itself. A namespace or default
 *      import, the `icons` map, a subpath (`lucide-react/dynamic`) or a
 *      dynamic import() can reach an alias by a name no linter can see.
 *   4. Stylesheets load no icon package. Rule 1 also applies to the target
 *      of every CSS `@import` (and Tailwind `@reference`, `@plugin`,
 *      `@config`), e.g. `@import "flag-icons/css/flag-icons.min.css"`.
 *
 * Biome (biome.json `overrides`) reports the common libraries in editors;
 * this script is what makes the rule complete. It checks the src/ beside it,
 * so the fixtures in test-fixtures/v1-boundary/ copy it into each tree.
 */
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { parse } from "@babel/parser";
import postcss from "postcss";
import valueParser from "postcss-value-parser";

const FRONTEND = path.join(import.meta.dirname, "..");
const ROOT = path.join(FRONTEND, "src", "v1");
const CODE = /\.(ts|tsx|mts|cts)$/;
// Every CSS language Vite knows, as in check-v1.mjs.
const STYLE = /\.(css|less|sass|scss|styl|stylus|pcss|postcss|sss)$/i;
const LIBRARY = "Lucide is the only icon library under src/v1";
const ICON_NAME = /icon|lucide/i;
/* Icon and flag sets whose package name has neither `icon` nor `lucide`. */
const KNOWN_ICON_PACKAGES = new Set([
  "react-feather",
  "react-world-flags",
  "react-flagkit",
  "flagpack",
]);
const KNOWN_ICON_SCOPES = ["@mdi/", "@fortawesome/"];
const isIconPackage = (pkg) =>
  ICON_NAME.test(pkg) ||
  KNOWN_ICON_PACKAGES.has(pkg) ||
  KNOWN_ICON_SCOPES.some((scope) => pkg.startsWith(scope));

/* alias -> canonical name, from the installed lucide-react's declarations. */
function lucideAliases() {
  const require = createRequire(path.join(FRONTEND, "package.json"));
  const dts = path.join(
    path.dirname(require.resolve("lucide-react/package.json")),
    "dist",
    "lucide-react.d.ts",
  );
  const aliases = new Map();
  const text = fs.readFileSync(dts, "utf8");
  for (const [, list] of text.matchAll(/^export \{([^}]*)\};?$/gm)) {
    for (const entry of list.split(",")) {
      const m = entry.trim().match(/^(?:type\s+)?(\w+) as (\w+)$/);
      if (!m) {
        continue;
      }
      const [, name, exported] = m;
      if (![name, `${name}Icon`, `Lucide${name}`].includes(exported)) {
        aliases.set(exported, name);
      }
    }
  }
  if (aliases.size === 0) {
    throw new Error(`no lucide-react aliases found in ${dts}`);
  }
  return aliases;
}

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (CODE.test(entry.name) || STYLE.test(entry.name)) {
      yield full;
    }
  }
}

function* nodes(node) {
  if (!node || typeof node.type !== "string") {
    return;
  }
  yield node;
  for (const [key, value] of Object.entries(node)) {
    if (key === "loc" || key.endsWith("Comments")) {
      continue;
    }
    for (const child of Array.isArray(value) ? value : [value]) {
      if (child && typeof child === "object") {
        yield* nodes(child);
      }
    }
  }
}

/* The package a bare specifier names, or null for a path or `@v1` alias. */
function packageOf(spec) {
  if (/^(\.|\/|@v1(\/|$)|@\/)/.test(spec)) {
    return null;
  }
  const parts = spec.split("/");
  return spec.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

const WRAPPERS = new Set([
  "TSAsExpression",
  "TSSatisfiesExpression",
  "TSNonNullExpression",
  "TSTypeAssertion",
  "ParenthesizedExpression",
]);

/* A string literal, or a template with no `${}`, through any TS wrapper. */
function staticText(arg) {
  let node = arg;
  while (node && WRAPPERS.has(node.type)) {
    node = node.expression;
  }
  if (node?.type === "StringLiteral") {
    return node.value;
  }
  if (node?.type === "TemplateLiteral" && node.expressions.length === 0) {
    return node.quasis[0].value.cooked;
  }
  return null;
}

const DECLARATIONS = new Set([
  "ImportDeclaration",
  "ExportNamedDeclaration",
  "ExportAllDeclaration",
]);

const isDynamicLoad = (node) =>
  node.type === "ImportExpression" ||
  (node.type === "CallExpression" &&
    (node.callee.type === "Import" ||
      (node.callee.type === "Identifier" && node.callee.name === "require")));

/*
 * { spec, specifiers } for an import-like node, else null. `specifiers` is
 * null when the names are not visible (dynamic load, `export *`), and [] for
 * a type-only `import("x")`. Arguments that are not static text are
 * check-v1's to reject as unanalysable.
 */
function importOf(node) {
  if (DECLARATIONS.has(node.type) && node.source) {
    const specifiers =
      node.type === "ExportAllDeclaration" ? null : node.specifiers;
    return { spec: node.source.value, specifiers };
  }
  if (isDynamicLoad(node)) {
    const spec = staticText(node.source ?? node.arguments?.[0]);
    return spec === null ? null : { spec, specifiers: null };
  }
  if (node.type === "TSImportType") {
    const spec = staticText(node.argument?.literal ?? node.argument);
    return spec === null ? null : { spec, specifiers: [] };
  }
  return null;
}

const importName = (n) => (n.type === "Identifier" ? n.name : n.value);

function checkFile(file, aliases, report) {
  const name = path.basename(file);
  const plugins = [["typescript", { dts: /\.d\.[mc]?ts$/.test(name) }]];
  if (name.endsWith(".tsx")) {
    plugins.push("jsx");
  }
  const ast = parse(fs.readFileSync(file, "utf8"), {
    sourceType: "module",
    plugins,
  });
  for (const node of nodes(ast.program)) {
    const found = importOf(node);
    if (!found) {
      continue;
    }
    const { spec, specifiers } = found;
    const pkg = spec && packageOf(spec);
    if (!pkg || !isIconPackage(pkg)) {
      continue;
    }
    const line = node.loc.start.line;
    if (pkg !== "lucide-react") {
      report(file, line, `${LIBRARY}; '${spec}' is not allowed.`);
      continue;
    }
    if (spec !== "lucide-react") {
      report(
        file,
        line,
        `${LIBRARY}; import from 'lucide-react' itself, not '${spec}'.`,
      );
      continue;
    }
    if (!specifiers) {
      report(
        file,
        line,
        "Import Lucide icons by name from 'lucide-react'; a dynamic import or `export *` can reach a deprecated alias.",
      );
      continue;
    }
    for (const s of specifiers) {
      if (
        s.type === "ImportNamespaceSpecifier" ||
        s.type === "ImportDefaultSpecifier" ||
        s.type === "ExportNamespaceSpecifier"
      ) {
        report(
          file,
          line,
          "Import Lucide icons by name from 'lucide-react', not as a namespace or default import.",
        );
        continue;
      }
      const imported = importName(
        s.type === "ExportSpecifier" ? s.local : s.imported,
      );
      if (imported === "icons") {
        report(
          file,
          line,
          "Do not use lucide-react's `icons` map; it is keyed by name, deprecated aliases included.",
        );
      } else if (aliases.has(imported)) {
        report(
          file,
          line,
          `Deprecated lucide-react alias '${imported}'; import the canonical name '${aliases.get(imported)}'.`,
        );
      }
    }
  }
}

// CSS `@import` and Tailwind's `@reference` / `@plugin` / `@config`.
const CSS_IMPORT_RULES = new Set(["import", "reference", "plugin", "config"]);

/* The target of an import at-rule: its first string, word or url(). A
 * CSS escape is undone and a leading `~` (the Sass/Less package prefix)
 * dropped. */
function cssImportTarget(params) {
  const first = valueParser(params).nodes.find((n) => n.type !== "space");
  const target =
    first?.type === "function" && first.value.toLowerCase() === "url"
      ? first.nodes.find((n) => n.type !== "space")?.value
      : first?.type === "string" || first?.type === "word"
        ? first.value
        : undefined;
  // Vite drops a backslash before any non-word character (`\@scope`).
  return target?.replace(/\\(\W)/g, "$1").replace(/^~/, "");
}

/* Unparseable CSS and unreadable targets are check-v1's to report. */
function checkCss(file, report) {
  let root;
  try {
    root = postcss.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return;
  }
  root.walkAtRules((rule) => {
    if (!CSS_IMPORT_RULES.has(rule.name.toLowerCase())) {
      return;
    }
    const spec = cssImportTarget(rule.params);
    const pkg = spec && packageOf(spec);
    if (pkg && isIconPackage(pkg)) {
      report(
        file,
        rule.source?.start?.line ?? 0,
        `${LIBRARY}; '${spec}' is not allowed.`,
      );
    }
  });
}

const problems = [];
if (fs.existsSync(ROOT)) {
  const aliases = lucideAliases();
  const report = (f, line, msg) =>
    problems.push(`${path.relative(FRONTEND, f)}:${line}  ${msg}`);
  for (const file of walk(ROOT)) {
    if (STYLE.test(file)) {
      checkCss(file, report);
    } else {
      checkFile(file, aliases, report);
    }
  }
}
for (const p of problems) {
  console.error(p);
}
if (problems.length) {
  console.error(`\ncheck-v1-icons: ${problems.length} problem(s).`);
  process.exit(1);
}
