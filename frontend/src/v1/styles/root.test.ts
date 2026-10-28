import fs from "node:fs";
import path from "node:path";
import { compile } from "@tailwindcss/node";
import { beforeAll, expect, it } from "vitest";
import { TOKENS } from "./tokens";

let css = "";
beforeAll(async () => {
  const base = path.resolve(import.meta.dirname);
  const source = fs.readFileSync(path.join(base, "index.css"), "utf8");
  const compiler = await compile(source, {
    base,
    onDependency: () => undefined,
  });
  css = compiler.build([
    "ui:bg-background",
    "ui:text-foreground",
    "ui:rounded-md",
    "ui:shadow-md",
    "ui:bg-scrim",
    "ui:text-body",
    "ui:text-overline",
    "ui:font-mono",
    "ui:focus-ring",
    "ui:dark:bg-card",
    "ui:unstract:bg-card",
    "ui:p-5",
    "bg-background",
    "flex",
    "ui:bg-red-500",
    "ui:text-sm",
    "ui:shadow-2xl",
    "ui:rounded-2xl",
  ]);
});

it("emits only prefixed utilities bound to runtime variables", () => {
  expect(css).toMatch(
    /\.ui\\:bg-background\s*\{[^}]*background-color:\s*var\(--background\)/,
  );
  expect(css).toMatch(
    /\.ui\\:rounded-md\s*\{[^}]*border-radius:\s*var\(--radius-md\)/,
  );
  expect(css).toMatch(/\.ui\\:shadow-md\s*\{/);
  expect(css).toMatch(
    /\.ui\\:text-body\s*\{[^}]*font-size:\s*var\(--type-body-size\)/,
  );
  expect(css).toMatch(
    // Tailwind wraps the tracking in --tw-tracking so a tracking-* utility can override it.
    /\.ui\\:text-overline\s*\{[^}]*letter-spacing:\s*var\((--tw-tracking,\s*var\()?--type-overline-tracking\)/,
  );
  expect(css).toMatch(/\.ui\\:focus-ring\s*\{/);
  expect(css).not.toMatch(/(^|[^\\:])\.bg-background\b/);
  expect(css).not.toMatch(/(^|[^\\:])\.flex\b/);
});

it("has no stock palette, text scale, shadow scale or radius scale", () => {
  expect(css).not.toContain("bg-red-500");
  expect(css).not.toContain("text-sm");
  expect(css).not.toContain("shadow-2xl");
  expect(css).not.toContain("rounded-2xl");
});

it("dark and unstract variants key on data-theme, never on prefers-color-scheme", () => {
  expect(css).toMatch(/\[data-theme="?dark"?\]/);
  expect(css).toMatch(/\[data-theme="?unstract"?\]/);
  expect(css).not.toContain("prefers-color-scheme");
});

it("every emitted rule is a ui: utility, scoped to .v1, or Tailwind's :root/property defaults", () => {
  const selectors = [...css.matchAll(/^\s*([^@{}\n][^{}\n]*)\{/gm)].map((m) =>
    m[1].trim(),
  );
  const unscoped = selectors.filter(
    (s) =>
      !/^(\.v1\b|\.ui\\:|:root, :host|\*, ::before, ::after, ::backdrop)/.test(
        s,
      ) && !s.startsWith("@"),
  );
  expect(unscoped).toEqual([]);
});

it("declares no !important, and every custom property is a Tailwind ui variable or a runtime token", () => {
  expect(css).not.toContain("!important");
  const tokenVars = new Set<string>(TOKENS.map((t) => t.cssVar));
  const declared = [...css.matchAll(/^\s*(--[\w-]+):/gm)].map((m) => m[1]);
  const strays = declared.filter(
    (v) =>
      !v.startsWith("--ui-") && !v.startsWith("--tw-") && !tokenVars.has(v),
  );
  expect(strays).toEqual([]);
});
