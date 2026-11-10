import type { ThemeMode } from "@v1/lib/theme";
import type { Token, TokenFamily } from "@v1/lib/tokens";
import source from "./tokens.json";

/**
 * The token values live in tokens.json, one array per family in board order.
 * Edit there, then run `bun run tokens:v1`. Each entry is `name`, `utility`,
 * `values` (one string when the value is the same in every mode, else one
 * per mode) and an optional `note`; the CSS variable is always `--` + name.
 *
 * Colour is the Midnight Bloom collection minus its palette entries (sky-300,
 * sky-500, openai-green, white), plus the code-* and diff-* syntax and diff
 * colours P1-T16 added and the chart ramp chart-1..chart-5. Spacing is one
 * 4pt scale: a value not on the list is a bug. Type is eight roles, each a size, a line height and a
 * weight. Elevation is one value per step. Focus has no offset: its colour
 * is the `ring` token.
 */
type TokenSource = Readonly<{
  name: string;
  utility: string;
  values: string | Readonly<Record<ThemeMode, string>>;
  note?: string;
}>;

const MODES: readonly ThemeMode[] = ["light", "dark", "unstract"];
// Board order; also the only keys tokens.json may have.
const FAMILIES: readonly TokenFamily[] = [
  "colour",
  "spacing",
  "radius",
  "type",
  "elevation",
  "focus",
  "font",
];

function values(
  family: TokenFamily,
  entry: TokenSource,
): Readonly<Record<ThemeMode, string>> {
  if (typeof entry.values === "string") {
    const value = entry.values;
    return { light: value, dark: value, unstract: value };
  }
  for (const mode of MODES) {
    if (typeof entry.values[mode] !== "string") {
      throw new Error(
        `tokens.json: ${family}/${entry.name} has no ${mode} value`,
      );
    }
  }
  return entry.values;
}

function fromSource(
  entries: Readonly<Record<string, readonly TokenSource[]>>,
): readonly Token[] {
  const families = Object.keys(entries);
  const unknown = families.filter(
    (f) => !(FAMILIES as readonly string[]).includes(f),
  );
  if (unknown.length > 0) {
    throw new Error(`tokens.json: unknown family ${unknown.join(", ")}`);
  }
  return FAMILIES.flatMap((family) =>
    (entries[family] ?? []).map((entry) => ({
      family,
      name: entry.name,
      cssVar: `--${entry.name}` as const,
      utility: entry.utility,
      values: values(family, entry),
      ...(entry.note === undefined ? {} : { note: entry.note }),
    })),
  );
}

/** Every token on the dev-spec board, in board order. */
export const TOKENS: readonly Token[] = fromSource(source);
