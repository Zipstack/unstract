import type { JSX } from "react";
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
}: ChartTooltipProps): JSX.Element | null {
  if (!active) {
    return null;
  }
  const row = payload?.[0]?.payload;
  const category =
    categoryKey === undefined
      ? label
      : typeof row === "object" && row !== null
        ? (row as Record<string, unknown>)[categoryKey]
        : undefined;
  // A live region (`output` has the status role), as Recharts' own tooltip is
  // under its accessibility layer: the arrow keys move this tooltip, and a
  // screen reader hears each move.
  return (
    <output
      data-slot="chart-tooltip"
      aria-live="assertive"
      className="ui:flex ui:min-w-40 ui:flex-col ui:gap-1.5 ui:rounded-md ui:border ui:border-border ui:bg-popover ui:px-3 ui:py-2 ui:text-caption ui:text-popover-foreground ui:shadow-md"
    >
      {typeof category === "string" || typeof category === "number" ? (
        <p className="ui:text-foreground">{fmt.x(category)}</p>
      ) : null}
      <ul className="ui:flex ui:flex-col ui:gap-1">
        {series.map((s) => {
          const value = payload?.find((p) => p.dataKey === s.key)?.value;
          return (
            <li key={s.key} className="ui:flex ui:items-center ui:gap-2">
              <span
                aria-hidden
                style={{ "--swatch": s.color }}
                className="ui:size-2 ui:shrink-0 ui:rounded-full ui:bg-(--swatch)"
              />
              <span className="ui:flex-1 ui:text-muted-foreground">
                {s.label}
              </span>
              <span className="ui:tabular-nums">
                {typeof value === "number" && Number.isFinite(value)
                  ? s.format(value)
                  : "–"}
              </span>
            </li>
          );
        })}
      </ul>
    </output>
  );
}
