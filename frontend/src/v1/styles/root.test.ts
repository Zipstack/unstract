import fs from "node:fs";
import path from "node:path";
import { compile } from "@tailwindcss/node";
import { beforeAll, expect, it } from "vitest";
import { TOKENS } from "./tokens";

const base = path.resolve(import.meta.dirname);
const source = fs.readFileSync(path.join(base, "index.css"), "utf8");
const CANDIDATES = [
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
  "ui:drop-shadow-lg",
  "ui:inset-shadow-sm",
  "ui:text-shadow-lg",
];

async function build(stylesheet: string): Promise<string> {
  const compiler = await compile(stylesheet, {
    base,
    onDependency: () => undefined,
  });
  return compiler.build(CANDIDATES);
}

/** Split a selector list on its top-level commas (not those inside :where() or [..]). */
function selectorParts(list: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of list) {
    if (ch === "(" || ch === "[") {
      depth++;
    }
    if (ch === ")" || ch === "]") {
      depth--;
    }
    if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  parts.push(current.trim());
  return parts;
}

// Each part must be a .v1-scoped selector, a ui: utility, or Tailwind's
// :root/:host theme layer and *, ::before, ::after, ::backdrop property defaults.
const ALLOWED_PART =
  /^(\.v1(?=[\s.:[#>~+]|$)|\.ui\\:|:root$|:host$|\*$|::before$|::after$|::backdrop$)/;

function unscopedParts(output: string): string[] {
  return [...output.matchAll(/^\s*([^@{}\n][^{}\n]*)\{/gm)]
    .map((m) => m[1].trim())
    .filter((list) => !list.startsWith("@"))
    .flatMap(selectorParts)
    .filter((part) => !ALLOWED_PART.test(part));
}

let css = "";
beforeAll(async () => {
  css = await build(source);
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
  expect(css).not.toMatch(/(^|[^\\:])\.bg-background\b/);
  expect(css).not.toMatch(/(^|[^\\:])\.flex\b/);
});

it("has no stock palette, text scale, shadow scales or radius scale", () => {
  expect(css).not.toContain("bg-red-500");
  expect(css).not.toContain("text-sm");
  expect(css).not.toContain("shadow-2xl");
  expect(css).not.toContain("rounded-2xl");
  expect(css).not.toContain("drop-shadow-lg");
  expect(css).not.toContain("inset-shadow-sm");
  expect(css).not.toContain("text-shadow-lg");
});

it("the focus ring keeps a transparent outline for forced-colors mode beside the box-shadow ring", () => {
  const rule = css.match(/\.ui\\:focus-ring\s*\{([^}]*)\}/)?.[1] ?? "";
  expect(rule).toMatch(/outline(-style)?:\s*(solid|2px solid transparent)/);
  expect(rule).toContain("border-color: var(--ring)");
  expect(rule).toContain(
    "color-mix(in srgb, var(--ring) var(--focus-ring-alpha), transparent)",
  );
});

it("dark and unstract variants key on the v1 root's data-theme, never on prefers-color-scheme", () => {
  // Name the variant rules and their binding: tokens.css alone also contains
  // [data-theme=…] selectors, so matching those would pass with no variants.
  expect(css).toMatch(
    /\.ui\\:dark\\:bg-card:where\(\.v1\[data-theme="?dark"?\],\s*\.v1\[data-theme="?dark"?\]\s*\*\s*\)\s*\{[^}]*background-color:\s*var\(--card\)/,
  );
  expect(css).toMatch(
    /\.ui\\:unstract\\:bg-card:where\(\.v1\[data-theme="?unstract"?\],\s*\.v1\[data-theme="?unstract"?\]\s*\*\s*\)\s*\{[^}]*background-color:\s*var\(--card\)/,
  );
  expect(css).not.toContain("prefers-color-scheme");
});

it("every emitted selector is a ui: utility, scoped to .v1, or Tailwind's :root/property defaults", async () => {
  expect(unscopedParts(css)).toEqual([]);
  // Negative proof: a leak hidden after a scoped selector in a list is caught.
  const leaky = await build(
    `${source}\n.v1 p, body { color: var(--foreground); }\n`,
  );
  expect(unscopedParts(leaky)).toEqual(["body"]);
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

it("only the app root fills and paints its area, so the portal container is not a painted block", () => {
  expect(css).toMatch(
    /\.v1\[data-ui-version="?v1"?\]\s*\{\s*min-height:\s*100%;\s*background-color:\s*var\(--background\);?\s*\}/,
  );
  expect(css).not.toMatch(/\.v1\s*\{[^}]*(min-height|background-color)/);
});
