#!/usr/bin/env node
/*
 * Build check for v1 plugins (src/v1/plugins/<id>/manifest.ts, copied in by
 * the cloud overlay). Under Bun it imports the TypeScript directly; under Node
 * it transpiles with esbuild, loaded only then, because the cloud overlay runs
 * this with Bun before any dependency is installed. Runs the registry's
 * conflict checks for every distribution and returns the distribution matrix. vite.config.js runs it in every build and publishes
 * the matrix as plugin-matrix.json.
 *
 *   node scripts/v1-plugins.mjs [out.json] [--dir plugins]   check, print or write the matrix
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DEFAULT_DIR = path.join(import.meta.dirname, "../src/v1/plugins");
const REGISTRY = path.join(
  import.meta.dirname,
  "../src/v1/lib/plugins/registry.ts",
);

const dataUrl = (code) =>
  `data:text/javascript;base64,${Buffer.from(code).toString("base64")}`;

const BUN = Boolean(process.versions.bun);

let registry;
function loadRegistry() {
  if (BUN) {
    registry ??= import(pathToFileURL(REGISTRY).href);
    return registry;
  }
  registry ??= import("esbuild")
    .then(({ build }) =>
      build({
        entryPoints: [REGISTRY],
        bundle: true,
        write: false,
        format: "esm",
        platform: "node",
      }),
    )
    .then((r) => import(dataUrl(r.outputFiles[0].text)));
  return registry;
}

async function importManifest(file) {
  if (BUN) {
    return import(pathToFileURL(file).href);
  }
  const { transform } = await import("esbuild");
  const { code } = await transform(fs.readFileSync(file, "utf8"), {
    loader: "ts",
    format: "esm",
    sourcefile: file,
  });
  return import(dataUrl(code));
}

async function load(dir, id) {
  const file = path.join(dir, id, "manifest.ts");
  const rel = `${id}/manifest.ts`;
  let mod;
  try {
    mod = await importManifest(file);
  } catch (err) {
    throw new Error(
      `${rel} could not be loaded (${err.message}). A manifest may only ` +
        '`import type`; load components with `() => import("./X")`.',
    );
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
  const manifests = await Promise.all(ids.map((id) => load(dir, id)));
  const { buildRegistry } = await loadRegistry();
  // Throws on any conflict in any distribution.
  const offered = (d) => [...buildRegistry(manifests, d).plugins];
  return {
    distributions: {
      oss: offered("oss"),
      cloud: offered("cloud"),
      onprem: offered("onprem"),
    },
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
  const out = args.find((a, i) => !a.startsWith("--") && i !== flag + 1);
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
      process.exit(1);
    });
}
