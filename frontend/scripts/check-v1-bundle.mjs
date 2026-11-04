#!/usr/bin/env node
/*
 * Bundle guard for the frontend v1 epic (P0-T10): a v1 chunk never pulls in
 * a v0 module or antd.
 *
 * Runs the production build (vite.config.js, unchanged) with one extra Rollup
 * plugin that records every output chunk: its entry module, the modules
 * bundled into it and the chunks it imports. Then, for every v1 chunk, it
 * walks the chunks that chunk loads (static and dynamic imports) and fails on
 * any module from src/ outside src/v1/ (v0, including the antd shims) or from
 * the antd packages.
 *
 * A v1 chunk is one whose entry module is under src/v1/, or whose own source
 * modules are all under src/v1/. A chunk that only shares vendor code
 * (node_modules) is neither v0 nor v1. Until v1 is loaded through its own
 * import (the version switch, P0-T03) the build has no v1 chunk and the guard
 * passes with nothing to check; the fixtures prove it fails on a bad tree.
 *
 *   (no flags)              Build, then check. The build is also the PR's
 *                           "v1 builds with no overlay" check.
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
 * as-is (absolute) for packages, null for virtual modules. */
function moduleName(id) {
  if (id.startsWith("\0")) {
    return null;
  }
  const file = id.split("?")[0];
  if (file.includes("/node_modules/")) {
    return file;
  }
  const rel = path.relative(FRONTEND, file).split(path.sep).join("/");
  return rel.startsWith("..") ? file : rel;
}

const byName = (a, b) => a.localeCompare(b);

function reporter(chunks) {
  return {
    name: "v1-bundle-report",
    apply: "build",
    generateBundle(_options, bundle) {
      for (const output of Object.values(bundle)) {
        if (output.type !== "chunk") {
          continue;
        }
        chunks.push({
          fileName: output.fileName,
          facade: output.facadeModuleId
            ? moduleName(output.facadeModuleId)
            : null,
          modules: Object.keys(output.modules)
            .map(moduleName)
            .filter(Boolean)
            .sort(byName),
          imports: [...output.imports, ...output.dynamicImports].sort(byName),
        });
      }
    },
  };
}

async function buildReport() {
  const { build } = await import("vite");
  const chunks = [];
  await build({
    root: FRONTEND,
    configFile: path.join(FRONTEND, "vite.config.js"),
    logLevel: "warn",
    plugins: [reporter(chunks)],
  });
  return { chunks };
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

function isV1Chunk(chunk) {
  if (chunk.facade) {
    return kind(chunk.facade) === "v1";
  }
  const own = chunk.modules.map(kind).filter((k) => k === "v1" || k === "v0");
  return own.length > 0 && own.every((k) => k === "v1");
}

/* Every chunk a v1 chunk loads, itself included, with the chunks in between. */
function reachable(root, chunksByName) {
  const seen = new Map([[root.fileName, []]]);
  const queue = [root];
  while (queue.length > 0) {
    const chunk = queue.shift();
    const via = [...seen.get(chunk.fileName), chunk.fileName];
    for (const next of chunk.imports) {
      const target = chunksByName.get(next);
      if (target && !seen.has(next)) {
        seen.set(next, via);
        queue.push(target);
      }
    }
  }
  return [...seen].map(([fileName, via]) => ({
    chunk: chunksByName.get(fileName),
    via,
  }));
}

function describe(root, name, path) {
  const what = kind(name) === "v0" ? "v0 module" : "antd module";
  const from = root.facade ? `, from ${root.facade}` : "";
  const where = path.length > 1 ? ` through ${path.join(" -> ")}` : "";
  return `${root.fileName} (v1${from}) pulls in ${what} ${name}${where}.`;
}

function check(report) {
  const chunksByName = new Map(
    report.chunks.map((chunk) => [chunk.fileName, chunk]),
  );
  const v1Chunks = report.chunks.filter(isV1Chunk);
  const problems = v1Chunks.flatMap((root) =>
    reachable(root, chunksByName).flatMap(({ chunk, via }) =>
      chunk.modules
        .filter((name) => ["v0", "antd"].includes(kind(name)))
        .map((name) => describe(root, name, [...via, chunk.fileName])),
    ),
  );
  return { v1Chunks: v1Chunks.length, problems };
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

const { v1Chunks, problems } = check(report);
if (problems.length > 0) {
  console.error(problems.join("\n"));
  console.error(
    `\ncheck-v1-bundle: ${problems.length} problem(s). v1 chunks may load only v1 code and packages other than antd.`,
  );
  process.exit(1);
}
console.log(
  `check-v1-bundle: ok (${report.chunks.length} chunk(s), ${v1Chunks} v1 chunk(s))`,
);
