import { type JSX, useEffect } from "react";
import type { Formatters } from "./describe";

export type TooltipEntry = Readonly<{
  dataKey?: unknown;
  value?: unknown;
  /** The hovered row, as Recharts plotted it. */
  payload?: unknown;
}>;

export type TooltipSeries = Readonly<{
  key: string;
  label: string;
  color: string;
  format: (value: number) => string;
}>;

type ChartTooltipProps = Readonly<{
  /** Set by Recharts, which clones this element with the hovered point. */
  active?: boolean;
  label?: unknown;
  payload?: readonly TooltipEntry[];
  series: readonly TooltipSeries[];
  fmt: Formatters;
  /**
   * Read the category from this field of the hovered row instead of from
   * Recharts' `label`, where the label is something else (a row index). The
   * row comes from Recharts with the values, so heading and values always
   * describe the same row.
   */
  categoryKey?: string;
  /**
   * Called with a sentence for the active point (category, then each series
   * and its value, "no data" for a gap), and with "" when Recharts reports
   * the tooltip inactive or this element unmounts. An Escape dismissal hides
   * the tooltip without either, so the last sentence stays. The chart puts it
   * in a live region that stays mounted, outside Recharts' tooltip wrapper.
   */
  onAnnounce?: (text: string) => void;
}>;

/**
 * Recharts' tooltip `content`, passed as an element (not a function, which
 * Recharts would mount as a new component type on every render): the
 * category, then one row per series with a swatch, its label and its value
 * (frame D14). A gap shows "–", as in the data table, so a category with no
 * values still names itself. Marker series never appear: only keys in
 * `series` are shown.
 */
export function ChartTooltip({
  active,
  label,
  payload,
  series,
  fmt,
  categoryKey,
  onAnnounce,
}: ChartTooltipProps): JSX.Element | null {
  const row = payload?.[0]?.payload;
  const category =
    categoryKey === undefined
      ? label
      : typeof row === "object" && row !== null
        ? (row as Record<string, unknown>)[categoryKey]
        : undefined;
  const heading =
    typeof category === "string" || typeof category === "number"
      ? fmt.x(category)
      : undefined;
  const rows = series.map((s) => {
    const value = payload?.find((p) => p.dataKey === s.key)?.value;
    const known = typeof value === "number" && Number.isFinite(value);
    return {
      series: s,
      text: known ? s.format(value) : "–",
      // Screen readers skip a lone dash, so a gap is said in words.
      spoken: known ? s.format(value) : "no data",
    };
  });
  const sentence = active
    ? [heading, rows.map((r) => `${r.series.label} ${r.spoken}`).join(", ")]
        .filter((part) => part !== undefined)
        .join(": ")
    : "";
  // Recharts keeps this element mounted while the tooltip is closed (it
  // re-renders it with `active` false), so the effect reports the close too.
  // The cleanup clears the sentence when this element unmounts while open
  // (the chart going to loading, or a sparkline's tooltip turned off).
  useEffect(() => {
    onAnnounce?.(sentence);
    return () => onAnnounce?.("");
  }, [onAnnounce, sentence]);
  if (!active) {
    return null;
  }
  return (
    <div
      data-slot="chart-tooltip"
      className="ui:flex ui:min-w-40 ui:flex-col ui:gap-1.5 ui:rounded-md ui:border ui:border-border ui:bg-popover ui:px-3 ui:py-2 ui:text-caption ui:text-popover-foreground ui:shadow-md"
    >
      {heading === undefined ? null : (
        <p className="ui:text-foreground">{heading}</p>
      )}
      <ul className="ui:flex ui:flex-col ui:gap-1">
        {rows.map(({ series: s, text }) => (
          <li key={s.key} className="ui:flex ui:items-center ui:gap-2">
            <span
              aria-hidden
              style={{ "--swatch": s.color }}
              className="ui:size-2 ui:shrink-0 ui:rounded-full ui:bg-(--swatch)"
            />
            <span className="ui:flex-1 ui:text-muted-foreground">
              {s.label}
            </span>
            <span className="ui:tabular-nums">{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
