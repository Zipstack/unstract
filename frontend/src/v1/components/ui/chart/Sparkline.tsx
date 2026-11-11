import { type JSX, useEffect, useId, useState } from "react";
import {
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from "recharts";
import {
  ChartFrame,
  DEFAULT_EMPTY_MESSAGE,
  DEFAULT_X_LABEL,
} from "./ChartFrame";
import { ChartTooltip } from "./ChartTooltip";
import {
  describeChart,
  type Formatters,
  formatCategory,
  formatValue,
  hasValues,
  tableRows,
  unparsedWarnings,
} from "./describe";
import { isolatedDot } from "./marks";
import { seriesColors } from "./palette";
import type { BaseChartProps, ChartDatum } from "./types";

export const DEFAULT_SPARKLINE_HEIGHT = 40;

const MARGIN = { top: 4, right: 2, bottom: 4, left: 2 };

export type SparklineProps<Row extends ChartDatum> = BaseChartProps<Row> &
  Readonly<{
    /** Shows a tooltip on hover and arrow keys. Default false. */
    tooltip?: boolean;
  }>;

/**
 * A small trend line for a KPI card (frame D01's four cards): no axes, grid or
 * legend, and no tooltip unless asked. Loading, empty and the text
 * alternative work as in the other charts.
 */
export function Sparkline<Row extends ChartDatum>({
  data,
  xKey,
  xLabel = DEFAULT_X_LABEL,
  series,
  title,
  summary,
  state = "ready",
  emptySlot,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  height = DEFAULT_SPARKLINE_HEIGHT,
  width,
  valueFormat = formatValue,
  xFormat = formatCategory,
  tooltip = false,
  className,
}: SparklineProps<Row>): JSX.Element {
  const summaryId = useId();
  // The active point's sentence, for the live region (see ChartTooltip).
  const [live, setLive] = useState("");
  const fmt: Formatters = { value: valueFormat, x: xFormat };
  const colors = seriesColors(series);
  const resolved =
    state === "ready" && !hasValues(data, series) ? "empty" : state;
  // An unparsed value reads as a gap, so a payload the page forgot to parse
  // shows the empty state; say why in the console (see CartesianChart).
  const warnings = JSON.stringify(unparsedWarnings(data, series));
  useEffect(() => {
    for (const warning of JSON.parse(warnings) as string[]) {
      console.warn(warning);
    }
  }, [warnings]);
  const text =
    summary ??
    describeChart({ kind: "sparkline", title, data, xKey, series, fmt });
  const chart = (
    <RechartsLineChart
      // The caller's array itself, so Recharts keeps its data store while it does.
      data={data as readonly ChartDatum[] as ChartDatum[]}
      margin={MARGIN}
      width={width}
      height={width === undefined ? undefined : height}
      aria-label={title}
      aria-describedby={summaryId}
      // Without a tooltip the keyboard layer has nothing to move, so the plot
      // stays out of the tab order.
      accessibilityLayer={tooltip}
      {...(tooltip ? {} : { role: "img" })}
    >
      {/* A series with axis "right" scales on its own hidden axis, as on the
          axis charts, so a small-valued series beside a large one is not flat. */}
      <YAxis yAxisId="left" hide domain={["dataMin", "dataMax"]} />
      {series.some((s) => s.axis === "right") ? (
        <YAxis yAxisId="right" hide domain={["dataMin", "dataMax"]} />
      ) : null}
      {tooltip ? (
        <Tooltip
          cursor={{ stroke: "var(--border)" }}
          isAnimationActive={false}
          filterNull={false}
          content={
            <ChartTooltip
              // The x key is not an axis here, so Recharts' label is the
              // row index; read the category from the hovered row instead.
              categoryKey={xKey}
              onAnnounce={setLive}
              series={series.map((s, i) => ({
                key: s.key,
                label: s.label,
                color: colors[i],
                format: s.format ?? valueFormat,
              }))}
              fmt={fmt}
            />
          }
        />
      ) : null}
      {series.map((s, i) => (
        <Line
          key={s.key}
          dataKey={s.key}
          yAxisId={s.axis ?? "left"}
          name={s.label}
          type="linear"
          stroke={colors[i]}
          strokeWidth={1.5}
          dot={isolatedDot(colors[i])}
          activeDot={
            tooltip ? { r: 3, stroke: "var(--card)", strokeWidth: 2 } : false
          }
          isAnimationActive={false}
        />
      ))}
    </RechartsLineChart>
  );
  return (
    <ChartFrame
      slot="sparkline"
      live={live}
      title={title}
      state={resolved}
      height={height}
      width={width}
      emptySlot={emptySlot}
      emptyMessage={emptyMessage}
      summary={text}
      summaryId={summaryId}
      table={{
        head: [xLabel, ...series.map((s) => s.label)],
        rows: tableRows(data, xKey, series, fmt),
      }}
      className={className}
    >
      {width === undefined ? (
        <ResponsiveContainer width="100%" height={height}>
          {chart}
        </ResponsiveContainer>
      ) : (
        chart
      )}
    </ChartFrame>
  );
}
