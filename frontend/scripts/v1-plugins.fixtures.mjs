// Fixtures for v1-plugins.mjs. Run with `node --test` (bun run test:v1).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { check } from "./v1-plugins.mjs";

function plugins(manifests) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v1-plugins-"));
  for (const [id, body] of Object.entries(manifests)) {
    fs.mkdirSync(path.join(dir, id));
    fs.writeFileSync(path.join(dir, id, "manifest.ts"), body);
  }
  return dir;
}

const manifest = (id, distributions, extra = "") => `
import type { PluginManifest } from "@v1/lib/plugins/types";
export const manifest = {
  id: "${id}",
  distributions: ${JSON.stringify(distributions)},
  ${extra}
} satisfies PluginManifest;
`;

test("the matrix lists each plugin per distribution", async () => {
  const dir = plugins({
    billing: manifest(
      "billing",
      ["cloud"],
      `slots: { "account-menu.plan-billing": () => import("./Billing") },
       routes: [{ path: "/billing", load: () => import("./Billing") }],`,
    ),
    switcher: manifest("switcher", ["cloud", "onprem"]),
  });
  assert.deepEqual(await check(dir), {
    distributions: {
      oss: [],
      cloud: ["billing", "switcher"],
      onprem: ["switcher"],
    },
    plugins: [
      {
        id: "billing",
        distributions: ["cloud"],
        slots: ["account-menu.plan-billing"],
        routes: ["/billing"],
      },
      {
        id: "switcher",
        distributions: ["cloud", "onprem"],
        slots: [],
        routes: [],
      },
    ],
  });
});

test("no plugins directory gives an empty matrix", async () => {
  assert.deepEqual(await check(path.join(os.tmpdir(), "v1-plugins-none")), {
    distributions: { oss: [], cloud: [], onprem: [] },
    plugins: [],
  });
});

test("a slot filled twice fails, naming both plugins", async () => {
  const slot = `slots: { "shell.product-switcher": () => import("./X") },`;
  const dir = plugins({
    a: manifest("a", ["cloud"], slot),
    b: manifest("b", ["cloud"], slot),
  });
  await assert.rejects(check(dir), /shell\.product-switcher.*\ba\b.*\bb\b/);
});

test("a manifest whose id differs from its folder fails", async () => {
  const dir = plugins({ billing: manifest("payments", ["cloud"]) });
  await assert.rejects(
    check(dir),
    /billing\/manifest\.ts declares id payments/,
  );
});

test("a manifest with a runtime import fails with a clear message", async () => {
  const dir = plugins({
    bad: `import { x } from "@v1/lib/plugins/registry";\nexport const manifest = x;\n`,
  });
  await assert.rejects(check(dir), /bad\/manifest\.ts.*import type/);
});

test("a slot id the contract does not define fails, naming the plugin", async () => {
  const dir = plugins({
    typo: manifest(
      "typo",
      ["cloud"],
      `slots: { "shell.product-swicher": () => import("./X") },`,
    ),
  });
  await assert.rejects(check(dir), /typo.*shell\.product-swicher/);
});

test("a distribution no build offers fails, naming the plugin", async () => {
  const dir = plugins({ stray: manifest("stray", ["cloud", "onprem-x"]) });
  await assert.rejects(check(dir), /stray.*onprem-x/);
});

test("a folder without a manifest fails, but dotfiles are ignored", async () => {
  const dir = plugins({ billing: manifest("billing", ["cloud"]) });
  fs.mkdirSync(path.join(dir, ".cache"));
  fs.writeFileSync(path.join(dir, "index.ts"), "export {};\n");
  assert.deepEqual((await check(dir)).distributions.cloud, ["billing"]);
  fs.mkdirSync(path.join(dir, "empty"));
  await assert.rejects(check(dir), /empty\/ has no manifest\.ts/);
});

const script = path.join(import.meta.dirname, "v1-plugins.mjs");
const cli = (dir) =>
  spawnSync(process.execPath, [script, "--dir", dir], { encoding: "utf8" });

test("the CLI exits 1 on a conflict, naming both plugins", () => {
  const slot = `slots: { "shell.product-switcher": () => import("./X") },`;
  const result = cli(
    plugins({
      a: manifest("a", ["cloud"], slot),
      b: manifest("b", ["cloud"], slot),
    }),
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /shell\.product-switcher.*\ba\b.*\bb\b/);
});

test("the CLI exits 0 and prints the matrix on a clean directory", () => {
  const result = cli(plugins({ billing: manifest("billing", ["cloud"]) }));
  assert.equal(result.status, 0);
  assert.deepEqual(JSON.parse(result.stdout).distributions.cloud, ["billing"]);
});
