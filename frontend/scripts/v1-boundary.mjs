#!/usr/bin/env node
/*
 * The v1 import boundary, in both directions, plus the v1-only bans.
 *
 *   node scripts/v1-boundary.mjs           all checks
 *   node scripts/v1-boundary.mjs files     file types only (typecheck:v1)
 *   node scripts/v1-boundary.mjs imports   imports and bans only (lint:v1)
 *
 * Biome can restrict package names but cannot resolve a relative path to
 * see where it lands, so the boundary lives here. Imports are found by
 * regex, not a parser.
 * ponytail: regex scan; it misses imports built at runtime, which v1's
 * lint already forbids by convention. Swap for a parser if that changes.
 */
import fs from "node:fs";
import path from "node:path";

const CODE = new Set([".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]);
const V1_CODE = new Set([".ts", ".tsx"]);
const V1_OTHER = new Set([
  ".md",
  ".svg",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".ico",
  ".woff",
  ".woff2",
  ".json",
]);
const BANNED = [/^prop-types$/, /^antd(\/|$)/, /^@ant-design\//];
const IMPORT_RES = [
  /\b(?:import|export)\s+(?:[^'"`;]*?\sfrom\s+)?["']([^"']+)["']/g,
  /\bimport\(\s*["']([^"']+)["']\s*\)/g,
  /\brequire\(\s*["']([^"']+)["']\s*\)/g,
];
const ANT_CLASS = /(?<![\w@/-])ant-[a-z]/;

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === "node_modules" ? [] : walk(full);
    }
    return [full];
  });
}

function lineOf(text, index) {
  return text.slice(0, index).split("\n").length;
}

// A file's folder for the "no relative paths across folders" rule:
// components/<x> and pages/<x> count as their own folders.
function folderOf(rel) {
  const [first, second] = rel.split(path.sep);
  return first === "components" || first === "pages"
    ? `${first}/${second}`
    : first;
}

export function check(src, mode = "all") {
  const v1 = path.join(src, "v1");
  const entry = path.join(v1, "index");
  const errors = [];
  const report = (file, line, message) =>
    errors.push(
      `${path.relative(src, file)}${line ? `:${line}` : ""}: ${message}`,
    );

  const resolve = (spec, file) => {
    if (spec.startsWith(".")) {
      return path.resolve(path.dirname(file), spec);
    }
    if (spec === "@v1" || spec.startsWith("@v1/")) {
      return path.join(v1, spec.slice(3));
    }
    if (spec.startsWith("@/")) {
      return path.join(src, spec.slice(2));
    }
    return null;
  };
  const inV1 = (p) => p === v1 || p.startsWith(v1 + path.sep);
  const isEntry = (p) => {
    const bare = p.replace(/\.(ts|tsx|js)$/, "");
    return p === v1 || bare === entry;
  };

  for (const file of walk(src)) {
    const ext = path.extname(file);
    const fromV1 = inV1(file);
    const rel = path.relative(v1, file);

    if (fromV1 && mode !== "imports") {
      const inStyles = rel.split(path.sep)[0] === "styles";
      if (ext === ".css" && !inStyles) {
        report(file, 0, "component .css files are not allowed; use styles/");
      } else if (
        !V1_CODE.has(ext) &&
        !V1_OTHER.has(ext) &&
        ext !== ".css" &&
        path.basename(file) !== ".gitkeep"
      ) {
        report(file, 0, "v1 is TypeScript only (.ts, .tsx)");
      }
    }
    if (mode === "files" || !CODE.has(ext)) {
      continue;
    }

    const text = fs.readFileSync(file, "utf8");
    if (fromV1) {
      const ant = text.match(ANT_CLASS);
      if (ant) {
        report(file, lineOf(text, ant.index), "the ant- class prefix is v0");
      }
    }
    for (const re of IMPORT_RES) {
      for (const m of text.matchAll(re)) {
        const spec = m[1];
        const line = lineOf(text, m.index);
        const target = resolve(spec, file);
        if (!fromV1) {
          if (target && inV1(target) && !isEntry(target)) {
            report(
              file,
              line,
              `v0 may import only the v1 public entry, not ${spec}`,
            );
          }
          continue;
        }
        if (target === null) {
          if (BANNED.some((b) => b.test(spec))) {
            report(file, line, `${spec} is not allowed in v1`);
          }
          continue;
        }
        if (!inV1(target)) {
          report(file, line, `${spec} resolves outside src/v1`);
          continue;
        }
        const targetRel = path.relative(v1, target);
        if (
          spec.endsWith(".css") &&
          targetRel.split(path.sep)[0] !== "styles"
        ) {
          report(file, line, `${spec}: v1 imports .css only from styles/`);
        }
        if (spec.startsWith(".") && folderOf(rel) !== folderOf(targetRel)) {
          report(
            file,
            line,
            `${spec} crosses folders; import it as @v1/${targetRel.split(path.sep).join("/")}`,
          );
        }
      }
    }
  }
  return errors;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const src = path.resolve(import.meta.dirname, "../src");
  const errors = check(src, process.argv[2]);
  for (const e of errors) {
    console.error(e);
  }
  process.exit(errors.length ? 1 : 0);
}
