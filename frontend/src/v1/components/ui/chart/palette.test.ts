import { THEME_MODES, type ThemeMode } from "@v1/lib/theme";
import { TOKENS } from "@v1/styles/tokens";
import { describe, expect, it } from "vitest";
import {
  CHART_RAMP_SIZE,
  rampColor,
  seriesColors,
  TONE_TOKENS,
} from "./palette";

function tokenValue(name: string, mode: ThemeMode): string {
  const token = TOKENS.find((t) => t.name === name);
  if (token === undefined) {
    throw new Error(`no token ${name}`);
  }
  return token.values[mode];
}

/** WCAG 2 relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (match === null) {
    throw new Error(`${hex} is not #rrggbb`);
  }
  const [r, g, b] = match.slice(1).map((part) => {
    const c = Number.parseInt(part, 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("legibility (WCAG 1.4.11: 3:1 for graphical objects)", () => {
  for (const mode of THEME_MODES) {
    const card = tokenValue("card", mode);
    it(`every ramp step reaches 3:1 against card in ${mode}`, () => {
      for (let step = 1; step <= CHART_RAMP_SIZE; step++) {
        const color = tokenValue(`chart-${step}`, mode);
        expect(
          contrast(color, card),
          `chart-${step} ${color} on ${card}`,
        ).toBeGreaterThanOrEqual(3);
      }
    });
    it(`every tone reaches 3:1 against card in ${mode}`, () => {
      for (const token of Object.values(TONE_TOKENS)) {
        const color = tokenValue(token, mode);
        expect(
          contrast(color, card),
          `${token} ${color} on ${card}`,
        ).toBeGreaterThanOrEqual(3);
      }
    });
  }

  it("the contrast helper matches known WCAG ratios", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
    expect(() => luminance("var(--card)")).toThrow();
  });
});

it("the ramp is ordered lightest to darkest in every mode", () => {
  for (const mode of THEME_MODES) {
    const lum = Array.from({ length: CHART_RAMP_SIZE }, (_, i) =>
      luminance(tokenValue(`chart-${i + 1}`, mode)),
    );
    const sorted = [...lum].sort((a, b) => b - a);
    expect(lum, mode).toEqual(sorted);
  }
});

it("ramp step n reads --chart-(n+1) and wraps after the fifth", () => {
  expect(rampColor(0)).toBe("var(--chart-1)");
  expect(rampColor(4)).toBe("var(--chart-5)");
  expect(rampColor(5)).toBe("var(--chart-1)");
});

it("untoned series take the ramp in order; toned series take their token and skip no step", () => {
  expect(
    seriesColors([
      { key: "a", label: "A" },
      { key: "b", label: "B", tone: "destructive" },
      { key: "c", label: "C" },
      { key: "d", label: "D", tone: "muted" },
      { key: "e", label: "E", tone: "primary" },
    ]),
  ).toEqual([
    "var(--chart-1)",
    "var(--destructive)",
    "var(--chart-2)",
    "var(--muted-foreground)",
    "var(--primary)",
  ]);
});
