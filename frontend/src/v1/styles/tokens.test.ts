import fs from "node:fs";
import path from "node:path";
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

it("token names and CSS variables are unique and runtime variables never use Tailwind's --v1- namespace", () => {
  expect(new Set(TOKENS.map((t) => t.name)).size).toBe(TOKENS.length);
  expect(new Set(TOKENS.map((t) => t.cssVar)).size).toBe(TOKENS.length);
  expect(TOKENS.filter((t) => t.cssVar.startsWith("--v1-"))).toEqual([]);
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
  expect(byFamily("colour")).toHaveLength(30); // the Midnight Bloom collection minus its four palette entries
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
