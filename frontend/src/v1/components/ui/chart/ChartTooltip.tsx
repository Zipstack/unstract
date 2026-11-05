import type { JSX } from "react";
import type { Formatters } from "./describe";

export type TooltipEntry = Readonly<{
  dataKey?: unknown;
  value?: unknown;
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
  /** Maps Recharts' label to the category, where it passes something else (a row index). */
  labelOf?: (label: unknown) => unknown;
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
  labelOf,
}: ChartTooltipProps): JSX.Element | null {
  if (!active) {
    return null;
  }
  const category = labelOf === undefined ? label : labelOf(label);
  return (
    <div
      data-slot="chart-tooltip"
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
    </div>
  );
}
