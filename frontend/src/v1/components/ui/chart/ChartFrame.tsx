import { Skeleton, SkeletonBlock } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import type { JSX, ReactNode } from "react";
import type { ChartState } from "./types";

export const DEFAULT_EMPTY_MESSAGE = "No data for this period";
export const DEFAULT_X_LABEL = "Category";

export type LegendItem = Readonly<{
  key: string;
  label: string;
  color: string;
}>;

type ChartFrameProps = Readonly<{
  slot: string;
  title: string;
  state: ChartState;
  height: number;
  width?: number;
  emptySlot?: ReactNode;
  emptyMessage: string;
  /** The text alternative: a sentence, and the data as a table. */
  summary: string;
  summaryId: string;
  table: Readonly<{ head: readonly string[]; rows: readonly string[][] }>;
  legend?: Readonly<{
    position: "top" | "bottom";
    items: readonly LegendItem[];
  }>;
  className?: string;
  children: ReactNode;
}>;

/**
 * What every chart shares around its plot: the loading and empty states, the
 * legend, and the text alternative (a summary sentence the plot points at
 * through aria-describedby, and a visually hidden table of every value).
 */
export function ChartFrame({
  slot,
  title,
  state,
  height,
  width,
  emptySlot,
  emptyMessage,
  summary,
  summaryId,
  table,
  legend,
  className,
  children,
}: ChartFrameProps): JSX.Element {
  // Runtime geometry reaches the classes through custom properties (styling rule S1).
  const sized = cn(
    "ui:h-(--chart-height)",
    width === undefined ? "ui:w-full" : "ui:w-(--chart-width)",
  );
  if (state === "loading") {
    return (
      <div
        data-slot={slot}
        data-state="loading"
        style={{
          "--chart-height": `${height}px`,
          "--chart-width": width === undefined ? undefined : `${width}px`,
        }}
        className={cn(sized, className)}
      >
        <Skeleton label={`Loading ${title}`}>
          <SkeletonBlock className="ui:h-(--chart-height)" />
        </Skeleton>
      </div>
    );
  }
  if (state === "empty") {
    return (
      <div
        data-slot={slot}
        data-state="empty"
        style={{
          "--chart-height": `${height}px`,
          "--chart-width": width === undefined ? undefined : `${width}px`,
        }}
        className={cn(
          sized,
          "ui:flex ui:items-center ui:justify-center",
          className,
        )}
      >
        {emptySlot ?? (
          <p className="ui:text-body-small ui:text-muted-foreground">
            <span className="ui:sr-only">{`${title}: `}</span>
            {emptyMessage}
          </p>
        )}
      </div>
    );
  }
  const legendList =
    legend === undefined || legend.items.length === 0 ? null : (
      <ul
        data-slot="chart-legend"
        className="ui:flex ui:flex-wrap ui:gap-x-4 ui:gap-y-1 ui:text-caption ui:text-muted-foreground"
      >
        {legend.items.map((item) => (
          <li
            key={item.key}
            className="ui:inline-flex ui:items-center ui:gap-1.5"
          >
            <span
              aria-hidden
              style={{ "--swatch": item.color }}
              className="ui:size-2 ui:shrink-0 ui:rounded-full ui:bg-(--swatch)"
            />
            {item.label}
          </li>
        ))}
      </ul>
    );
  return (
    <div
      data-slot={slot}
      data-state="ready"
      style={{
        "--chart-height": `${height}px`,
        "--chart-width": width === undefined ? undefined : `${width}px`,
      }}
      className={cn(
        "ui:flex ui:flex-col ui:gap-3",
        width === undefined ? "ui:w-full" : "ui:w-(--chart-width)",
        className,
      )}
    >
      {legend?.position === "top" ? legendList : null}
      <div className={cn(sized, "ui:text-caption")}>{children}</div>
      {legend?.position === "bottom" ? legendList : null}
      <p id={summaryId} className="ui:sr-only">
        {summary}
      </p>
      <table data-slot="chart-table" className="ui:sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            {table.head.map((cell, c) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: columns follow series order, and labels may repeat.
              <th key={c} scope="col">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: rows follow data order, and categories may repeat.
            <tr key={r}>
              {row.map((cell, c) =>
                c === 0 ? (
                  // biome-ignore lint/suspicious/noArrayIndexKey: cells follow series order.
                  <th key={c} scope="row">
                    {cell}
                  </th>
                ) : (
                  // biome-ignore lint/suspicious/noArrayIndexKey: cells follow series order.
                  <td key={c}>{cell}</td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
