import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DatePicker } from "@/components/ui/shims/antd-datetime";
import { Form } from "@/components/ui/shims/antd-form";
import { Input, Radio, Select } from "@/components/ui/shims/antd-inputs";
import { Collapse, Dropdown, Modal } from "@/components/ui/shims/antd-overlays";
import {
  Card,
  Layout,
  List,
  Table,
  Tabs,
} from "@/components/ui/shims/antd-structure";
import { Typography } from "@/components/ui/shims/antd-typography";

/**
 * Guard against the failure mode that took down Prompt Studio in the dev
 * deployment: a call-site renders `<Collapse.Panel>`, the shim never defined
 * it, React gets `undefined` as an element type and throws #130 — killing the
 * whole route, not just that component.
 *
 * The per-component tests could not catch it, because nothing rendered the
 * sub-component. So this test scans the SOURCE for every `<Foo.Bar>` usage and
 * asserts the shims actually expose it.
 */

const SHIMS = {
  Card,
  Collapse,
  Dropdown,
  Modal,
  DatePicker,
  Form,
  Input,
  Layout,
  List,
  Radio,
  Select,
  Table,
  Tabs,
  Typography,
};

/** Every `<Foo.Bar …>` in the app source, excluding the shims themselves. */
function collectSubComponentUsages() {
  // ../../.. — this file lives in src/components/ui/shims/, so three levels
  // up is `src/`. It was "../.." before the shims moved into their own
  // directory; left unchanged it would have silently scanned only
  // src/components/ and quietly reduced this guard's coverage.
  const root = path.resolve(import.meta.dirname, "../../..");
  /*
   * Assert the scan root, because getting it wrong does NOT fail this test —
   * it silently scans a smaller tree and finds nothing to complain about. The
   * shims move from `ui/` to `ui/shims/` changed the required depth from
   * "../.." to "../../..", and every assertion below still passed with the
   * stale value while covering only part of the app.
   */
  if (path.basename(root) !== "src") {
    throw new Error(
      `shim-completeness scan root must be src/, got ${root}. ` +
        "Fix the relative depth rather than the assertion.",
    );
  }
  const found = new Set();
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "node_modules") {
          continue;
        }
        walk(full);
        continue;
      }
      if (!entry.name.endsWith(".jsx") || entry.name.includes(".test.")) {
        continue;
      }
      // The shims themselves are the definition, not a call-site.
      if (full.includes(`${path.sep}shims${path.sep}antd-`)) {
        continue;
      }
      // Strip comments first: a doc comment mentioning `Modal.confirm` is not
      // a call-site, and flagging it would train people to ignore this test.
      const src = fs
        .readFileSync(full, "utf8")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "");
      // <Foo.Bar> in JSX
      for (const m of src.matchAll(/<([A-Z]\w+)\.(\w+)[\s/>]/g)) {
        found.add(`${m[1]}.${m[2]}`);
      }
      // Foo.bar(...) statics — antd exposed imperative APIs this way
      // (Modal.useModal, Modal.confirm). Undefined ones throw a TypeError
      // on click rather than at render, so they are just as fatal.
      for (const m of src.matchAll(/\b([A-Z]\w+)\.(\w+)\s*\(/g)) {
        found.add(`${m[1]}.${m[2]}`);
      }
    }
  };
  walk(root);
  return [...found].sort();
}

describe("shim completeness — every <Foo.Bar> used must be defined", () => {
  const usages = collectSubComponentUsages();

  it("finds sub-component usages to check", () => {
    expect(usages.length).toBeGreaterThan(0);
  });

  for (const usage of usages) {
    const [parent, child] = usage.split(".");
    if (!(parent in SHIMS)) {
      continue;
    }

    it(`${usage} is defined`, () => {
      const value = SHIMS[parent]?.[child];
      expect(
        value,
        `<${usage}> is rendered in the app but ${parent}.${child} is undefined. ` +
          "React throws error #130 for this and the whole route fails to load.",
      ).toBeDefined();
    });
  }
});
