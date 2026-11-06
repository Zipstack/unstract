import { THEME_MODES, type ThemeMode } from "@v1/lib/theme";
import { TOKENS } from "@v1/styles/tokens";
import { expect, it } from "vitest";
import { CHART_RAMP_SIZE, rampColor, seriesColors } from "./palette";

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

/*
 * The ramp is the LLMWhisperer design's --mode-* tokens, per mode, exactly as
 * in Figma (`figq tokens llmw`: Midnight Bloom, modes Light | Dark | Unstract).
 */
const DESIGNED_RAMP: Record<ThemeMode, readonly string[]> = {
  light: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
  dark: ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"],
  unstract: ["#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#104281"],
};

it("the ramp is the designed --mode-* values in every mode", () => {
  for (const mode of THEME_MODES) {
    const ramp = Array.from({ length: CHART_RAMP_SIZE }, (_, i) =>
      tokenValue(`chart-${i + 1}`, mode),
    );
    expect(ramp, mode).toEqual(DESIGNED_RAMP[mode]);
  }
});

it("the luminance helper follows WCAG 2 and rejects anything but #rrggbb", () => {
  expect(luminance("#ffffff")).toBeCloseTo(1, 5);
  expect(luminance("#000000")).toBe(0);
  // Each primary pins its own weight.
  expect(luminance("#ff0000")).toBeCloseTo(0.2126, 4);
  expect(luminance("#00ff00")).toBeCloseTo(0.7152, 4);
  expect(luminance("#0000ff")).toBeCloseTo(0.0722, 4);
  // Mid-grey is on the power segment of the sRGB curve. 5/255 is on the
  // linear one, far enough below the knee that the power formula misses it.
  expect(luminance("#777777")).toBeCloseTo(0.1845, 4);
  expect(luminance("#050505")).toBeCloseTo(0.0015176, 7);
  expect(luminance("#FFFFFF")).toBeCloseTo(1, 5);
  for (const bad of ["var(--card)", "#ffffff80", "x#ffffff", "#fff"]) {
    expect(() => luminance(bad)).toThrow(`${bad} is not #rrggbb`);
  }
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
