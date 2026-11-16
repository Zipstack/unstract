// Fixtures for v1-plugins.mjs. Run with `node --test` (bun run test:v1).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { after, test } from "node:test";
import { check } from "./v1-plugins.mjs";

const temps = [];
after(() => {
  for (const dir of temps) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

function tempDir(prefix) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
  temps.push(dir);
  return dir;
}

function plugins(manifests) {
  const dir = tempDir("v1-plugins-");
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
  const none = path.join(tempDir("v1-plugins-"), "none");
  assert.deepEqual(await check(none), {
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

test("a manifest with a syntax error fails with its cause and no import hint", async () => {
  const dir = plugins({ broken: "export const manifest = {\n" });
  await assert.rejects(check(dir), (err) => {
    assert.match(err.message, /broken\/manifest\.ts could not be loaded/);
    assert.doesNotMatch(err.message, /import type/);
    assert.ok(err.cause, "keeps the original error as its cause");
    return true;
  });
});

test("a manifest whose slot or route is not a loader fails, naming the plugin", async () => {
  for (const [extra, why] of [
    [
      `slots: { "shell.product-switcher": undefined },`,
      /odd fills slot shell\.product-switcher with undefined/,
    ],
    [`routes: [{ path: "/odd", load: "./Odd" }],`, /odd route \/odd has no load/],
    [`routes: [{ load: () => import("./X") }],`, /odd route 0 has no string path/],
  ]) {
    const dir = plugins({ odd: manifest("odd", ["cloud"], extra) });
    await assert.rejects(check(dir), why);
  }
});

for (const [route, why] of [
  ["/:orgName/v1-demo/:id?", /segment ':id\?'/],
  ["billing", /must start with \//],
]) {
  test(`a plugin route ${route} the route registry's pattern rule refuses fails`, async () => {
    const dir = plugins({
      odd: manifest(
        "odd",
        ["cloud"],
        `routes: [{ path: "${route}", load: () => import("./X") }],`,
      ),
    });
    await assert.rejects(check(dir), /odd route .* is not accepted/);
    await assert.rejects(check(dir), why);
  });
}

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

// DEMO_PAGES in app/registry/entries.ts declares /:orgName/v1-demo. A route
// the router would match for the same URLs clashes too.
for (const route of [
  "/:orgName/v1-demo",
  "/:org/v1-demo",
  "/:orgName/V1-Demo",
  "/:orgName/*",
]) {
  test(`a plugin route ${route} on a page OSS declares fails, naming OSS and the plugin`, async () => {
    const dir = plugins({
      clash: manifest(
        "clash",
        ["cloud"],
        `routes: [{ path: "${route}", load: () => import("./X") }],`,
      ),
    });
    await assert.rejects(check(dir), /\/:orgName\/v1-demo.*\bOSS\b.*\bclash\b/);
  });
}

test("a plugin route that only shares a prefix with an OSS page passes", async () => {
  const dir = plugins({
    near: manifest(
      "near",
      ["cloud"],
      `routes: [{ path: "/:orgName/v1-demo-x", load: () => import("./X") }],`,
    ),
  });
  assert.deepEqual((await check(dir)).distributions.cloud, ["near"]);
});

test("the Vite plugin fails the build on a conflict", async () => {
  const slot = `slots: { "shell.product-switcher": () => import("./X") },`;
  const dir = plugins({
    a: manifest("a", ["cloud"], slot),
    b: manifest("b", ["cloud"], slot),
  });
  const { v1PluginMatrix } = await import("../vite.config.js");
  await assert.rejects(
    v1PluginMatrix({ dir, distribution: "cloud" }).buildStart(),
    /shell\.product-switcher.*\ba\b.*\bb\b/,
  );
});

test("the Vite plugin emits plugin-matrix.json naming the build's distribution", async () => {
  const dir = plugins({ billing: manifest("billing", ["cloud"]) });
  const { v1PluginMatrix } = await import("../vite.config.js");
  const plugin = v1PluginMatrix({ dir, distribution: "cloud" });
  await plugin.buildStart();
  const emitted = [];
  plugin.generateBundle.call({ emitFile: (file) => emitted.push(file) });
  assert.equal(emitted.length, 1);
  assert.equal(emitted[0].fileName, "plugin-matrix.json");
  const matrix = JSON.parse(emitted[0].source);
  assert.equal(matrix.distribution, "cloud");
  assert.deepEqual(matrix.distributions.cloud, ["billing"]);
});

test("the Vite config accepts every distribution the route registry declares", async () => {
  const { distributions } = await check(tempDir("v1-plugins-"));
  const { default: config } = await import("../vite.config.js");
  const saved = process.env.VITE_DISTRIBUTION;
  try {
    for (const d of Object.keys(distributions)) {
      process.env.VITE_DISTRIBUTION = d;
      assert.doesNotThrow(() => config({ mode: "production" }), d);
    }
  } finally {
    if (saved === undefined) {
      delete process.env.VITE_DISTRIBUTION;
    } else {
      process.env.VITE_DISTRIBUTION = saved;
    }
  }
});

test("the Vite config runs the plugin matrix in every build", async () => {
  const { default: config } = await import("../vite.config.js");
  const names = config({ mode: "production" }).plugins.map((p) => p.name);
  assert.ok(names.includes("v1-plugin-matrix"), names.join(", "));
});

test("vite build fails on a VITE_DISTRIBUTION it does not know", async () => {
  const { default: config } = await import("../vite.config.js");
  const saved = process.env.VITE_DISTRIBUTION;
  process.env.VITE_DISTRIBUTION = "on-prem";
  try {
    assert.throws(() => config({ mode: "production" }), /on-prem/);
  } finally {
    if (saved === undefined) {
      delete process.env.VITE_DISTRIBUTION;
    } else {
      process.env.VITE_DISTRIBUTION = saved;
    }
  }
});

test("both frontend image stages that run Vite take VITE_DISTRIBUTION", () => {
  const dockerfile = fs.readFileSync(
    path.join(
      import.meta.dirname,
      "../../docker/dockerfiles/frontend.Dockerfile",
    ),
    "utf8",
  );
  const stages = Object.fromEntries(
    dockerfile
      .split(/^FROM /m)
      .slice(1)
      .map((stage) => [stage.match(/ AS (\S+)/)?.[1], stage]),
  );
  for (const name of ["development", "builder"]) {
    assert.match(stages[name], /^ARG VITE_DISTRIBUTION=/m, `${name} stage`);
  }
  assert.match(
    stages.development,
    /^ENV VITE_DISTRIBUTION=\$\{VITE_DISTRIBUTION\}/m,
  );
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

test("the CLI prints the cause of a manifest that fails to load", () => {
  const result = cli(plugins({ broken: "export const manifest = {\n" }));
  assert.equal(result.status, 1);
  assert.match(result.stderr, /broken\/manifest\.ts could not be loaded/);
  // The cause follows the message, with its stack.
  assert.match(result.stderr, /^\s+at /m);
});

test("the CLI writes the matrix to the file argument, with or without --dir", () => {
  const out = path.join(tempDir("v1-out-"), "m.json");
  // Without --dir it reads V1_PLUGINS_DIR, not the repository's plugins/.
  const bare = spawnSync(process.execPath, [script, out], {
    encoding: "utf8",
    env: {
      ...process.env,
      V1_PLUGINS_DIR: plugins({ switcher: manifest("switcher", ["onprem"]) }),
    },
  });
  assert.equal(bare.status, 0, bare.stderr);
  assert.equal(bare.stdout, "");
  const fromEnv = JSON.parse(fs.readFileSync(out, "utf8"));
  assert.deepEqual(fromEnv.distributions.onprem, ["switcher"]);

  const dir = plugins({ billing: manifest("billing", ["cloud"]) });
  const before = spawnSync(process.execPath, [script, out, "--dir", dir], {
    encoding: "utf8",
  });
  assert.equal(before.status, 0, before.stderr);
  const matrix = JSON.parse(fs.readFileSync(out, "utf8"));
  assert.deepEqual(matrix.distributions.cloud, ["billing"]);
});
