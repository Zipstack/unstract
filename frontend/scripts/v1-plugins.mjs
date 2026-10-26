#!/usr/bin/env node
/*
 * Build check for v1 plugins (src/v1/plugins/<id>/manifest.ts, copied in by
 * the cloud overlay). Loads every manifest with Node or Bun type stripping,
 * runs the registry's conflict checks for every distribution, and returns the
 * distribution matrix. vite.config.js runs it in every build and publishes
 * the matrix as plugin-matrix.json.
 *
 *   node scripts/v1-plugins.mjs [out.json]   check, print or write the matrix
 */
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { buildRegistry } from "../src/v1/lib/plugins/registry.ts";

const DEFAULT_DIR = path.join(import.meta.dirname, "../src/v1/plugins");

async function load(dir, id) {
  const file = path.join(dir, id, "manifest.ts");
  const rel = `${id}/manifest.ts`;
  let mod;
  try {
    mod = await import(pathToFileURL(file).href);
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
        .filter((e) => fs.existsSync(path.join(dir, e.name, "manifest.ts")))
        .map((e) => e.name)
        .sort()
    : [];
  const manifests = await Promise.all(ids.map((id) => load(dir, id)));
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
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  check()
    .then((matrix) => {
      const json = `${JSON.stringify(matrix, null, 2)}\n`;
      const out = process.argv[2];
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
