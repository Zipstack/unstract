import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * antd's Modal wrapper is statically positioned, so app CSS could set
 * `top: 20px` on a modal root and get "20px from the top of the viewport".
 *
 * The shadcn Dialog is `position: fixed` and centres itself with
 * `top: 50%` + `translateY(-50%)`. The same rule now overrides the centring,
 * and the transform pulls the dialog ABOVE the viewport — the header ends up
 * clipped off-screen. That is exactly what happened to `.prompt-studio-modal`,
 * and it was invisible in jsdom because there is no layout engine.
 *
 * This guards the whole stylesheet set rather than the one rule that bit us.
 */

const CSS_ROOT = path.resolve(import.meta.dirname, "../..");

function collectCssFiles(dir, acc = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules") {
        continue;
      }
      collectCssFiles(full, acc);
      continue;
    }
    if (entry.name.endsWith(".css")) {
      acc.push(full);
    }
  }
  return acc;
}

/**
 * Selectors that target a modal/dialog ROOT — not an element inside one.
 * `.foo-modal` and `.foo-modal.bar` count; `.foo-modal__body` and
 * `.foo-modal .thing` do not, since those are children and cannot fight the
 * root's positioning.
 */
function isModalRootSelector(selector) {
  const trimmed = selector.trim();
  if (/\s/.test(trimmed)) {
    return false;
  }
  if (trimmed.includes("__") || trimmed.includes(">")) {
    return false;
  }
  if (trimmed.includes(".ant-")) {
    return false;
  }
  return /modal|dialog/i.test(trimmed);
}

describe("CSS that would fight the Dialog's centring", () => {
  const files = collectCssFiles(CSS_ROOT);

  it("finds stylesheets to check", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it("no modal root sets `top`, `bottom` or `transform`", () => {
    const offenders = [];

    for (const file of files) {
      const css = fs.readFileSync(file, "utf8");
      for (const match of css.matchAll(/([^{}]+)\{([^}]*)\}/g)) {
        const [, rawSelector, body] = match;
        for (const selector of rawSelector.split(",")) {
          if (!isModalRootSelector(selector)) {
            continue;
          }
          const bad = body.match(/(^|;)\s*(top|bottom|transform)\s*:[^;]*/i);
          if (bad) {
            offenders.push(
              `${path.basename(file)}  ${selector.trim()}  {${bad[0].trim()}}`,
            );
          }
        }
      }
    }

    expect(
      offenders,
      "These rules position a modal ROOT. The Dialog centres itself with " +
        "top:50% + translateY(-50%), so they override the centring and push " +
        "the dialog off-screen. Move the offset to an inner element, or drop " +
        "it and let the component centre.\n  " +
        offenders.join("\n  "),
    ).toEqual([]);
  });
});
