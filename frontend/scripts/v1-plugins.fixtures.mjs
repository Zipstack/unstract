// Fixtures for v1-plugins.mjs. Run with `node --test` (bun run test:v1).
import assert from "node:assert/strict";
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
