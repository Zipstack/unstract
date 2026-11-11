import fs from "node:fs";
import path from "node:path";
import { TYPE_ROLES } from "@v1/lib/cn";
import { THEME_MODES } from "@v1/lib/theme";
import { renderTokensCss, renderTokenTable } from "@v1/lib/tokens";
import { expect, it } from "vitest";
import { TOKENS } from "./tokens";

it("every token is defined in every mode with a non-empty value", () => {
  for (const token of TOKENS) {
    for (const mode of THEME_MODES) {
      expect(token.values[mode], `${token.name} in ${mode}`).toMatch(/\S/);
    }
  }
});

it("token names and CSS variables are unique and runtime variables never use Tailwind's --ui- namespace", () => {
  expect(new Set(TOKENS.map((t) => t.name)).size).toBe(TOKENS.length);
  expect(new Set(TOKENS.map((t) => t.cssVar)).size).toBe(TOKENS.length);
  expect(TOKENS.filter((t) => t.cssVar.startsWith("--ui-"))).toEqual([]);
});

it("covers the families the board defines", () => {
  const byFamily = (f: string) =>
    TOKENS.filter((t) => t.family === f).map((t) => t.name);
  expect(byFamily("radius")).toEqual([
    "radius-sm",
    "radius-md",
    "radius-lg",
    "radius-xl",
  ]);
  expect(byFamily("spacing")).toEqual([
    "space-1",
    "space-2",
    "space-3",
    "space-4",
    "space-5",
    "space-6",
    "space-8",
  ]);
  expect(byFamily("elevation")).toEqual([
    "shadow-sm",
    "shadow-md",
    "shadow-lg",
    "shadow-xl",
    "scrim",
  ]);
  expect(byFamily("type")).toHaveLength(25); // eight roles × (size, line-height, weight) + overline tracking
  // The Midnight Bloom collection minus its four palette entries (30), plus
  // the ten syntax and diff colours P1-T16 adds and the five chart ramp steps.
  expect(byFamily("colour")).toHaveLength(45);
  for (const name of [
    "background",
    "foreground",
    "card",
    "popover",
    "primary",
    "primary-muted",
    "secondary",
    "muted",
    "accent",
    "destructive",
    "success",
    "warning",
    "border",
    "input",
    "ring",
    "sidebar",
    "sidebar-muted-foreground",
    "header",
  ]) {
    expect(byFamily("colour")).toContain(name);
  }
  for (const name of ["sky-300", "sky-500", "openai-green", "white"]) {
    expect(byFamily("colour")).not.toContain(name);
  }
  expect(byFamily("font")).toEqual(["font-sans", "font-mono"]);
  expect(byFamily("focus")).toEqual(["focus-ring-width", "focus-ring-alpha"]);
});

it("cn's type roles are exactly the roles of the type family, in order", () => {
  const roles = TOKENS.filter((t) => t.family === "type").map((t) =>
    t.name
      .replace(/^type-/, "")
      .replace(/-(size|line-height|weight|tracking)$/, ""),
  );
  expect([...TYPE_ROLES]).toEqual([...new Set(roles)]);
});

it("Unstract mode is the navy theme from the collection, not a copy of light", () => {
  const value = (n: string) => TOKENS.find((t) => t.name === n)?.values;
  expect(value("primary")).toEqual({
    light: "#6f5cef",
    dark: "#6f5cef",
    unstract: "#072b4d",
  });
  expect(value("sidebar")).toEqual({
    light: "#ffffff",
    dark: "#171717",
    unstract: "#0e3963",
  });
  expect(value("border")).toEqual({
    light: "#e5e5e5",
    dark: "#2e2e2e",
    unstract: "#e4e7eb",
  });
});

it("radii carry the four board values", () => {
  const value = (n: string) => TOKENS.find((t) => t.name === n)?.values.light;
  expect([
    value("radius-sm"),
    value("radius-md"),
    value("radius-lg"),
    value("radius-xl"),
  ]).toEqual(["6px", "8px", "10px", "14px"]);
});

it("generated tokens.css matches the source", () => {
  const css = fs.readFileSync(
    path.resolve(import.meta.dirname, "tokens.css"),
    "utf8",
  );
  expect(css).toBe(renderTokensCss(TOKENS));
});

it("the token table matches the dev-spec snapshot", async () => {
  await expect(renderTokenTable(TOKENS)).toMatchFileSnapshot(
    "./__snapshots__/token-table.md",
  );
});

/** WCAG relative luminance of `#rrggbb`. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** `#rrggbbaa` laid over an opaque `#rrggbb`. */
function over(tint: string, base: string): string {
  const alpha = Number.parseInt(tint.slice(7, 9), 16) / 255;
  return `#${[1, 3, 5]
    .map((i) => {
      const top = Number.parseInt(tint.slice(i, i + 2), 16);
      const bottom = Number.parseInt(base.slice(i, i + 2), 16);
      return Math.round(top * alpha + bottom * (1 - alpha))
        .toString(16)
        .padStart(2, "0");
    })
    .join("")}`;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// axe's color-contrast rule is off in the harness (tests load no CSS), so the
// code colours are checked here, on every surface they are drawn on.
it("code and diff text colours meet WCAG AA (4.5:1) on every surface they sit on, in every mode", () => {
  const value = (name: string, mode: (typeof THEME_MODES)[number]) =>
    TOKENS.find((t) => t.name === name)?.values[mode] as string;
  const text = TOKENS.filter(
    (t) => t.name.startsWith("code-") || /^diff-.*-foreground$/.test(t.name),
  ).map((t) => t.name);
  expect(text).toHaveLength(8);
  for (const mode of THEME_MODES) {
    const card = value("card", mode);
    const surfaces = {
      muted: value("muted", mode),
      card,
      // The active JsonView row.
      accent: value("accent", mode),
      added: over(value("diff-added", mode), card),
      removed: over(value("diff-removed", mode), card),
    };
    for (const name of text) {
      for (const [surface, colour] of Object.entries(surfaces)) {
        expect(
          contrast(value(name, mode), colour),
          `${name} on ${surface} in ${mode}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  }
});
