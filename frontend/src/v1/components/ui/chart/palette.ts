import type { ChartDatum, ChartSeries, ChartTone } from "./types";

/** Steps in the ordinal ramp (`--chart-1` lightest to `--chart-5` darkest, in every mode). */
export const CHART_RAMP_SIZE = 5;

/** The token each tone reads. */
export const TONE_TOKENS: Readonly<Record<ChartTone, string>> = {
  primary: "primary",
  destructive: "destructive",
  success: "success",
  warning: "warning",
  muted: "muted-foreground",
};

/** `var(--chart-n)` for ramp step `step` (0-based); wraps after the fifth. */
export function rampColor(step: number): string {
  return `var(--chart-${(step % CHART_RAMP_SIZE) + 1})`;
}

/**
 * One colour per series, in series order. A series with a `tone` takes that
 * token; the rest take the ramp in order, so the first untoned series is
 * `--chart-1` whatever comes before it.
 */
export function seriesColors<Row extends ChartDatum>(
  series: readonly ChartSeries<Row>[],
): string[] {
  let step = 0;
  return series.map((s) => {
    if (s.tone !== undefined) {
      return `var(--${TONE_TOKENS[s.tone]})`;
    }
    const color = rampColor(step);
    step += 1;
    return color;
  });
}
