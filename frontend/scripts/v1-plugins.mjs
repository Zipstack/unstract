#!/usr/bin/env node
/*
 * Build check for v1 plugins (src/v1/plugins/<id>/manifest.ts, copied in by
 * the cloud overlay). Under Bun it imports the TypeScript directly; under Node
 * it transpiles with esbuild, loaded only then, because the cloud overlay runs
 * this with Bun before any dependency is installed. Runs the registry's
 * shape and conflict checks for every distribution, including plugin routes
 * on pages the v1 route registry declares and route paths its pattern rule
 * rejects, and returns the distribution matrix.
 * vite.config.js runs it in every build and publishes the matrix as
 * plugin-matrix.json.
 *
 *   node scripts/v1-plugins.mjs [out.json] [--dir plugins]   check, print or write the matrix
 *
 * V1_PLUGINS_DIR replaces the default plugins folder (the fixtures use it).
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_DIR = process.env.V1_PLUGINS_DIR
  ? path.resolve(process.env.V1_PLUGINS_DIR)
  : path.join(import.meta.dirname, "../src/v1/plugins");
const SRC = path.join(import.meta.dirname, "../src/v1");
const REGISTRY = path.join(SRC, "lib/plugins/registry.ts");
// The v1 route registry's pages, its pattern rules and its distributions.
const ROUTE_ENTRIES = path.join(SRC, "app/registry/entries.ts");
const ROUTE_PATTERNS = path.join(SRC, "app/registry/patterns.ts");
const ROUTE_TYPES = path.join(SRC, "app/registry/types.ts");

const dataUrl = (code) =>
  `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;

const BUN = Boolean(process.versions.bun);

/** Imports a source module with its own imports; under Node, bundled by esbuild. */
function loadSource(file) {
  if (BUN) {
    return import(pathToFileURL(file).href);
  }
  return import("esbuild")
    .then(({ build }) =>
      build({
        entryPoints: [file],
        bundle: true,
        write: false,
        format: "esm",
        platform: "node",
      }),
    )
    .then((r) => import(dataUrl(r.outputFiles[0].text)));
}

/** A function that imports a manifest; under Node it loads esbuild first. */
async function manifestImporter() {
  if (BUN) {
    return (file) => import(pathToFileURL(file).href);
  }
  const { transform } = await import("esbuild");
  return async (file) => {
    const { code } = await transform(fs.readFileSync(file, "utf8"), {
      loader: "ts",
      format: "esm",
      sourcefile: file,
    });
    return import(dataUrl(code));
  };
}

// Node from a data: URL, Node from a file, Bun, esbuild.
const UNRESOLVED =
  /ERR_UNSUPPORTED_RESOLVE_REQUEST|ERR_MODULE_NOT_FOUND|Cannot find module|Could not resolve/;

const unresolved = (err) =>
  UNRESOLVED.test(`${err?.code ?? ""} ${err?.message ?? ""}`);

async function load(importManifest, dir, id) {
  const file = path.join(dir, id, "manifest.ts");
  const rel = `${id}/manifest.ts`;
  let mod;
  try {
    mod = await importManifest(file);
  } catch (err) {
    const hint = unresolved(err)
      ? ' A manifest may only `import type`; load components with `() => import("./X")`.'
      : "";
    throw new Error(`${rel} could not be loaded (${err?.message}).${hint}`, {
      cause: err,
    });
  }
  const { manifest } = mod;
  if (!manifest) {
    throw new Error(`${rel} does not export \`manifest\``);
  }
  if (manifest.id !== id) {
    throw new Error(
      `${rel} declares id ${manifest.id}; it must match its folder`,
    );
  }
  return manifest;
}

export async function check(dir = DEFAULT_DIR) {
  const ids = fs.existsSync(dir)
    ? fs
        .readdirSync(dir, { withFileTypes: true })
        .filter((e) => e.isDirectory() && !e.name.startsWith("."))
        .map((e) => e.name)
        .sort()
    : [];
  for (const id of ids) {
    if (!fs.existsSync(path.join(dir, id, "manifest.ts"))) {
      throw new Error(`${id}/ has no manifest.ts`);
    }
  }
  const importManifest = await manifestImporter();
  const manifests = await Promise.all(
    ids.map((id) => load(importManifest, dir, id)),
  );
  const [
    { buildRegistry },
    { PAGES, DEMO_PAGES },
    { patternProblem, patternsOverlap },
    { DISTRIBUTIONS },
  ] = await Promise.all([
    loadSource(REGISTRY),
    loadSource(ROUTE_ENTRIES),
    loadSource(ROUTE_PATTERNS),
    loadSource(ROUTE_TYPES),
  ]);
  const rules = {
    // Demo pages count: an E2E build registers them.
    ossRoutes: [...PAGES, ...DEMO_PAGES].flatMap((p) => p.v1Routes),
    overlaps: patternsOverlap,
    patternProblem,
  };
  // Throws on any conflict in any distribution.
  const offered = (d) => [...buildRegistry(manifests, d, rules).plugins];
  return {
    distributions: Object.fromEntries(DISTRIBUTIONS.map((d) => [d, offered(d)])),
    plugins: manifests.map((m) => ({
      id: m.id,
      distributions: [...m.distributions],
      slots: Object.keys(m.slots ?? {}),
      routes: (m.routes ?? []).map((r) => r.path),
    })),
  };
}

// No top-level await: vite.config.js imports this file and Vite bundles the
// config as CommonJS.
const isMain =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(fs.realpathSync(process.argv[1])).href;

if (isMain) {
  const args = process.argv.slice(2);
  const flag = args.indexOf("--dir");
  const dir = flag === -1 ? DEFAULT_DIR : path.resolve(args[flag + 1]);
  const out = args.find(
    (a, i) => !a.startsWith("--") && (flag === -1 || i !== flag + 1),
  );
  check(dir)
    .then((matrix) => {
      const json = `${JSON.stringify(matrix, null, 2)}\n`;
      if (out) {
        fs.writeFileSync(out, json);
      } else {
        process.stdout.write(json);
      }
    })
    .catch((err) => {
      console.error(`v1-plugins: ${err.message}`);
      if (err.cause) {
        console.error(err.cause);
      }
      process.exit(1);
    });
}
