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
  active?: boolean;
  label?: unknown;
  payload?: readonly TooltipEntry[];
  series: readonly TooltipSeries[];
  fmt: Formatters;
}>;

/**
 * Recharts' tooltip `content`: the category, then one row per series with a
 * swatch, its label and its value (frame D14). Marker series never appear:
 * only keys in `series` are shown.
 */
export function ChartTooltip({
  active,
  label,
  payload,
  series,
  fmt,
}: ChartTooltipProps): JSX.Element | null {
  if (!active || payload === undefined || payload.length === 0) {
    return null;
  }
  const rows = series.flatMap((s) => {
    const entry = payload.find((p) => p.dataKey === s.key);
    const value = entry?.value;
    return typeof value === "number" && Number.isFinite(value)
      ? [{ ...s, value }]
      : [];
  });
  if (rows.length === 0) {
    return null;
  }
  return (
    <div
      data-slot="chart-tooltip"
      className="ui:flex ui:min-w-40 ui:flex-col ui:gap-1.5 ui:rounded-md ui:border ui:border-border ui:bg-popover ui:px-3 ui:py-2 ui:text-caption ui:text-popover-foreground ui:shadow-md"
    >
      {typeof label === "string" || typeof label === "number" ? (
        <p className="ui:text-foreground">{fmt.x(label)}</p>
      ) : null}
      <ul className="ui:flex ui:flex-col ui:gap-1">
        {rows.map((row) => (
          <li key={row.key} className="ui:flex ui:items-center ui:gap-2">
            <span
              aria-hidden
              style={{ "--swatch": row.color }}
              className="ui:size-2 ui:shrink-0 ui:rounded-full ui:bg-(--swatch)"
            />
            <span className="ui:flex-1 ui:text-muted-foreground">
              {row.label}
            </span>
            <span className="ui:tabular-nums">{row.format(row.value)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
