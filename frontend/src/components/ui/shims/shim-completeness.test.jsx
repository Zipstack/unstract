import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import * as antdButton from "@/components/ui/shims/antd-button";
import * as antdDatetime from "@/components/ui/shims/antd-datetime";
import * as antdForm from "@/components/ui/shims/antd-form";
import * as antdInputs from "@/components/ui/shims/antd-inputs";
import * as antdLayout from "@/components/ui/shims/antd-layout";
import * as antdLeaves from "@/components/ui/shims/antd-leaves";
import * as antdOverlays from "@/components/ui/shims/antd-overlays";
import * as antdStructure from "@/components/ui/shims/antd-structure";
import * as antdTypography from "@/components/ui/shims/antd-typography";

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

/*
 * Built from every shim module's exports rather than hand-listed. The listed
 * form is opt-in coverage, and what it omits it omits silently: `Tree` and
 * `Steps` were both missing, so `<Tree.DirectoryTree>` — undefined, and the
 * whole Configure Connector modal throwing #130 the moment a connector was
 * picked — passed this guard. Adding a shim component must not also require
 * remembering to add it here.
 */
const SHIMS = Object.fromEntries(
  [
    antdButton,
    antdDatetime,
    antdForm,
    antdInputs,
    antdLayout,
    antdLeaves,
    antdOverlays,
    antdStructure,
    antdTypography,
  ].flatMap((mod) =>
    Object.entries(mod).filter(([name]) => /^[A-Z]/.test(name)),
  ),
);

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
  let scanned = 0;
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
      // .tsx as well as .jsx: the shim layer is being converted to TypeScript
      // file by file, and a `.jsx`-only filter would quietly stop scanning
      // each file as it converts — the scan still passes, just over less.
      if (!/\.[jt]sx$/.test(entry.name) || entry.name.includes(".test.")) {
        continue;
      }
      // The shims themselves are the definition, not a call-site.
      if (full.includes(`${path.sep}shims${path.sep}antd-`)) {
        continue;
      }
      scanned += 1;
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
      /*
       * `const { Bar } = Foo;` — the form antd's own docs use, and the one
       * that hid the DirectoryTree break: FileSystem.jsx lifts the static out
       * at module scope and renders a bare `<DirectoryTree>`, so neither
       * pattern above ever sees a `Tree.` prefix to check. It read as covered
       * because `<Tabs.TabPane>` happens to appear inline somewhere else.
       */
      for (const m of src.matchAll(
        /const\s*\{([^}]*)\}\s*=\s*([A-Z]\w+)\s*;/g,
      )) {
        for (const part of m[1].split(",")) {
          const key = part.split(/[:=]/)[0].trim();
          if (key) {
            found.add(`${m[2]}.${key}`);
          }
        }
      }
    }
  };
  walk(root);
  return { usages: [...found].sort(), scanned };
}

describe("shim completeness — every <Foo.Bar> used must be defined", () => {
  const { usages, scanned } = collectSubComponentUsages();

  it("finds sub-component usages to check", () => {
    expect(usages.length).toBeGreaterThan(0);
  });

  /*
   * This scan has silently narrowed twice: once when the shims moved to
   * ui/shims/ and the "../.." depth went stale, and once when the extension
   * filter still said `.jsx` after files began converting to `.tsx`. Both
   * times every assertion below still passed, over a fraction of the app.
   *
   * `usages.length > 0` does not catch that — one surviving file keeps it
   * true. A floor on the number of files actually read does. 275 match
   * today; 200 leaves room for ordinary churn while a dropped extension or
   * a wrong root (which cost ~all of them) fails loudly.
   */
  it("scans the whole app, not a subset", () => {
    expect(
      scanned,
      "shim-completeness scanned far fewer files than expected — the walk " +
        "root or the extension filter has drifted, so the assertions below " +
        "are covering only part of the app.",
    ).toBeGreaterThan(200);
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
