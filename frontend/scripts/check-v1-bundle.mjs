#!/usr/bin/env node
/*
 * Bundle guard for the frontend v1 epic (P0-T10): no v1 module reaches a v0
 * module or antd in the production module graph.
 *
 * Runs the production build (vite.config.js, unchanged) with one extra Rollup
 * plugin that records the module graph Rollup resolved: for every module, the
 * modules it imports statically and dynamically. Then, from every module
 * under src/v1/, it walks that graph and fails on any module from src/
 * outside src/v1/ (v0, including the antd shims) or from the antd packages.
 *
 * It judges imports, not chunk placement. Rollup may put a package v1 uses
 * into a chunk that also holds v0 code, and v1 may be inlined into a v0
 * chunk; neither changes what v1 code depends on. What the per-file import
 * check (check-v1.mjs) cannot see, and this guard can, is a package that
 * reaches antd or v0 code transitively.
 *
 * The graph covers only modules the build reaches. Until v1 is loaded through
 * its own import (the version switch, P0-T03) the build reaches no v1 module
 * and the guard passes with nothing to check; the fixtures prove it fails on
 * a bad tree.
 *
 *   (no flags)              Build, then check.
 *   --report <file>         Check a saved report instead of building.
 *   --save-report <file>    Build, write the report there, then check.
 */
import fs from "node:fs";
import path from "node:path";

const FRONTEND = path.join(import.meta.dirname, "..");
const ANTD = /\/node_modules\/(antd|@ant-design\/[^/]+)\//;

function usage(message) {
  console.error(`check-v1-bundle: ${message}`);
  console.error(
    "usage: check-v1-bundle.mjs [--report <file> | --save-report <file>]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  const opts = { report: null, saveReport: null };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const key = { "--report": "report", "--save-report": "saveReport" }[arg];
    if (!key) {
      usage(`unknown argument '${arg}'`);
    }
    const value = argv[i + 1];
    if (!value || value.startsWith("--")) {
      usage(`${arg} needs a value`);
    }
    opts[key] = value;
    i += 1;
  }
  if (opts.report && opts.saveReport) {
    usage("pass at most one of --report and --save-report");
  }
  return opts;
}

/* A module id as the report keeps it: frontend-relative for our sources,
 * as-is (absolute) for packages. Virtual modules stay in the graph, because
 * edges run through them: Rollup reaches a CommonJS module through
 * "\0<file>?commonjs-…", which is named after <file> so the walk continues
 * into it. One with no file behind it ("\0commonjsHelpers.js") is
 * "virtual:<id>", never v1, v0 or antd. */
function moduleName(id) {
  const file = id.replace(/^\0/, "").split("?")[0];
  if (!file) {
    return null;
  }
  if (!path.isAbsolute(file)) {
    return `virtual:${file}`;
  }
  if (file.includes("/node_modules/")) {
    return file;
  }
  const rel = path.relative(FRONTEND, file).split(path.sep).join("/");
  return rel.startsWith("..") ? file : rel;
}

const byName = (a, b) => a.localeCompare(b);

/* Records { module: [modules it imports] } for every module in the build. */
function reporter(graph) {
  return {
    name: "v1-bundle-report",
    apply: "build",
    generateBundle() {
      for (const id of this.getModuleIds()) {
        const name = moduleName(id);
        const info = this.getModuleInfo(id);
        if (!name || !info) {
          continue;
        }
        const deps = [...info.importedIds, ...info.dynamicallyImportedIds]
          .map(moduleName)
          .filter((dep) => dep && dep !== name);
        // A file and its virtual wrapper share a name, so merge their edges.
        graph[name] = [...new Set([...(graph[name] ?? []), ...deps])].sort(
          byName,
        );
      }
    },
  };
}

async function buildReport() {
  const { build } = await import("vite");
  const modules = {};
  await build({
    root: FRONTEND,
    configFile: path.join(FRONTEND, "vite.config.js"),
    logLevel: "warn",
    plugins: [reporter(modules)],
  });
  return { modules };
}

const kind = (name) => {
  if (ANTD.test(name)) {
    return "antd";
  }
  if (name.startsWith("src/v1/")) {
    return "v1";
  }
  if (name.startsWith("src/")) {
    return "v0";
  }
  return "other";
};

/* Every module reachable from root, with the modules in between. */
function reachable(root, modules) {
  const seen = new Map([[root, []]]);
  const queue = [root];
  while (queue.length > 0) {
    const name = queue.shift();
    const via = [...seen.get(name), name];
    for (const next of modules[name] ?? []) {
      if (!seen.has(next)) {
        seen.set(next, via);
        queue.push(next);
      }
    }
  }
  return seen;
}

function describe(target, via) {
  const what = kind(target) === "v0" ? "v0 module" : "antd module";
  const where = via.length > 1 ? ` through ${via.slice(1).join(" -> ")}` : "";
  return `${via[0]} (v1) reaches ${what} ${target}${where}.`;
}

function check(report) {
  const modules = report.modules ?? {};
  const v1Modules = Object.keys(modules)
    .filter((name) => kind(name) === "v1")
    .sort(byName);
  // One line per forbidden module, from the first v1 module that reaches it.
  const problems = new Map();
  for (const root of v1Modules) {
    for (const [target, via] of reachable(root, modules)) {
      if (["v0", "antd"].includes(kind(target)) && !problems.has(target)) {
        problems.set(target, describe(target, via));
      }
    }
  }
  return { v1Modules: v1Modules.length, problems: [...problems.values()] };
}

const opts = parseArgs(process.argv.slice(2));
let report;
if (opts.report) {
  try {
    report = JSON.parse(fs.readFileSync(opts.report, "utf8"));
  } catch (error) {
    console.error(
      `check-v1-bundle: cannot read ${opts.report}: ${error.message}`,
    );
    process.exit(2);
  }
} else {
  report = await buildReport();
  if (opts.saveReport) {
    fs.writeFileSync(opts.saveReport, `${JSON.stringify(report, null, 2)}\n`);
  }
}

const { v1Modules, problems } = check(report);
if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(
    `\ncheck-v1-bundle: ${problems.length} problem(s). v1 code may reach only v1 code and packages other than antd.`,
  );
  process.exit(1);
}
console.log(
  `check-v1-bundle: ok (${Object.keys(report.modules ?? {}).length} module(s), ${v1Modules} v1 module(s))`,
);
