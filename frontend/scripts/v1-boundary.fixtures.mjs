// Fixtures for v1-boundary.mjs. Run with `node --test` (bun run test:v1).
// Named *.fixtures.mjs so the v0 vitest glob never collects it.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { check } from "./v1-boundary.mjs";

function tree(files) {
  const src = fs.mkdtempSync(path.join(os.tmpdir(), "v1-boundary-"));
  for (const [file, body] of Object.entries(files)) {
    const full = path.join(src, file);
    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, body);
  }
  return src;
}

const ENTRY = { "v1/index.ts": "export const V1_PUBLIC_ENTRY = 'v1';\n" };

function errors(files, mode) {
  return check(tree({ ...ENTRY, ...files }), mode);
}

test("a v1 file importing a v0 helper fails", () => {
  const out = errors({
    "helpers/date.js": "export const d = 1;\n",
    "v1/lib/a.ts": 'import { d } from "../../helpers/date";\nexport { d };\n',
  });
  assert.equal(out.length, 1);
  assert.match(out[0], /v1\/lib\/a\.ts:1: .*outside src\/v1/);
});

test("a v1 file importing v0 through the @/ alias fails", () => {
  const out = errors({
    "v1/lib/a.ts": 'import x from "@/helpers/date";\nexport { x };\n',
  });
  assert.match(out.join("\n"), /outside src\/v1/);
});

test("a v0 file importing a non-entry v1 module fails", () => {
  const out = errors({
    "v1/lib/a.ts": "export const a = 1;\n",
    "pages/Home.jsx": 'import { a } from "../v1/lib/a";\n',
    "pages/Other.jsx": 'import { a } from "@v1/lib/a";\n',
  });
  assert.equal(out.length, 2);
  assert.match(out.join("\n"), /pages\/Home\.jsx:1: .*public entry/);
});

test("v0 importing the public entry passes", () => {
  const out = errors({
    "a.jsx": 'import { V1_PUBLIC_ENTRY } from "@v1";\n',
    "b.jsx": 'import "./v1";\n',
    "c.jsx": 'const m = import("./v1/index");\n',
  });
  assert.deepEqual(out, []);
});

test("a JavaScript file under v1 fails the file check", () => {
  const out = errors({ "v1/lib/legacy.js": "export const a = 1;\n" }, "files");
  assert.match(out.join("\n"), /legacy\.js: .*TypeScript only/);
});

test("a component .css file fails; styles/ may hold CSS", () => {
  const out = errors({
    "v1/styles/global.css": "body{}\n",
    "v1/app/main.ts": 'import "@v1/styles/global.css";\n',
    "v1/components/ui/Button.css": ".b{}\n",
    "v1/components/ui/Button.tsx": 'import "./Button.css";\n',
  });
  assert.equal(out.length, 2);
  assert.match(out.join("\n"), /Button\.css: .*styles\//);
  assert.match(out.join("\n"), /Button\.tsx:1: .*\.css/);
});

test("prop-types, antd and @ant-design are banned in v1", () => {
  const out = errors({
    "v1/lib/a.ts":
      'import PropTypes from "prop-types";\nimport { Button } from "antd";\nimport { X } from "@ant-design/icons";\nexport { PropTypes, Button, X };\n',
  });
  assert.equal(out.length, 3);
});

test("an ant- class name fails", () => {
  const out = errors({
    "v1/components/ui/A.tsx": 'export const c = "ant-btn primary";\n',
  });
  assert.match(out.join("\n"), /A\.tsx:1: .*ant-/);
});

test("relative imports may not cross folders; the alias may", () => {
  const out = errors({
    "v1/lib/a.ts": "export const a = 1;\n",
    "v1/lib/b.ts": 'import { a } from "./a";\nexport { a };\n',
    "v1/stores/s.ts": 'import { a } from "../lib/a";\nexport { a };\n',
    "v1/hooks/h.ts": 'import { a } from "@v1/lib/a";\nexport { a };\n',
  });
  assert.equal(out.length, 1);
  assert.match(out[0], /stores\/s\.ts:1: .*@v1\//);
});

test("multi-line and type-only imports are seen", () => {
  const out = errors({
    "v1/lib/a.ts":
      'import type {\n  Foo,\n} from "../../types/foo";\nexport type { Foo };\n',
  });
  assert.match(out.join("\n"), /v1\/lib\/a\.ts:1: .*outside src\/v1/);
});

test("the real scaffold is clean", () => {
  const src = path.resolve(import.meta.dirname, "../src");
  assert.deepEqual(check(src), []);
});
