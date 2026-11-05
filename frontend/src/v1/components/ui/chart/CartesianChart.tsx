import { type JSX, useId, useMemo } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartFrame,
  DEFAULT_EMPTY_MESSAGE,
  DEFAULT_X_LABEL,
} from "./ChartFrame";
import { ChartTooltip } from "./ChartTooltip";
import {
  type ChartKind,
  describeChart,
  type Formatters,
  formatAxisValue,
  formatCategory,
  formatValue,
  tableRows,
} from "./describe";
import { keptLabels, keptMarkers, markerKey, markerRows } from "./markers";
import { barMarker, isolatedDot, markerDot } from "./marks";
import { seriesColors } from "./palette";
import type { CartesianChartProps, ChartDatum } from "./types";

export const DEFAULT_CHART_HEIGHT = 240;

const NO_MARKERS: readonly never[] = [];

const AXIS_TICK = { fill: "var(--muted-foreground)" };
// Room for a marker label above the highest point.
const MARGIN = { top: 20, right: 8, bottom: 0, left: 0 };

type Props<Row extends ChartDatum> = CartesianChartProps<Row> &
  Readonly<{ kind: Exclude<ChartKind, "sparkline">; slot: string }>;

/** The shared body of LineChart, AreaChart, BarChart and StackedBarChart. */
export function CartesianChart<Row extends ChartDatum>({
  kind,
  slot,
  data,
  xKey,
  xLabel = DEFAULT_X_LABEL,
  series,
  title,
  summary,
  state = "ready",
  emptySlot,
  emptyMessage = DEFAULT_EMPTY_MESSAGE,
  height = DEFAULT_CHART_HEIGHT,
  width,
  valueFormat = formatValue,
  xFormat = formatCategory,
  axisFormat = formatAxisValue,
  rightAxisFormat = axisFormat,
  markers = NO_MARKERS,
  legend = "bottom",
  grid = true,
  className,
}: Props<Row>): JSX.Element {
  const summaryId = useId();
  const fmt: Formatters = { value: valueFormat, x: xFormat };
  const colors = seriesColors(series);
  const stacked = kind === "stacked-bar";
  const bars = kind === "bar" || stacked;
  const resolved = data.length === 0 && state === "ready" ? "empty" : state;
  // Memoised so the rows Recharts receives keep their identity while data,
  // series and markers do; a fresh array resets its data store every render.
  const kept = useMemo(
    () => keptMarkers(data, series, markers),
    [data, series, markers],
  );
  const rows = useMemo(
    () => [...(bars ? data : markerRows(data, series, kept))],
    [bars, data, series, kept],
  );
  const hasRight = series.some((s) => s.axis === "right");
  const text =
    summary ??
    describeChart({
      kind,
      title,
      data,
      xKey,
      series,
      markerLabels: keptLabels(kept),
      fmt,
    });
  const tooltipSeries = series.map((s, i) => ({
    key: s.key,
    label: s.label,
    color: colors[i],
    format: s.format ?? valueFormat,
  }));

  const marks = series.map((s, i) => {
    const axis = s.axis ?? "left";
    const common = {
      dataKey: s.key,
      name: s.label,
      yAxisId: axis,
      isAnimationActive: false,
    };
    switch (kind) {
      case "line":
        return (
          <Line
            key={s.key}
            {...common}
            type="linear"
            stroke={colors[i]}
            strokeWidth={2}
            dot={isolatedDot(colors[i], data, s.key)}
            activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
            connectNulls={false}
          />
        );
      case "area":
        return (
          <Area
            key={s.key}
            {...common}
            type="linear"
            stroke={colors[i]}
            strokeWidth={2}
            fill={colors[i]}
            fillOpacity={0.12}
            dot={isolatedDot(colors[i], data, s.key)}
            activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
          />
        );
      default:
        // Stacked segments are split by a 1px card-coloured stroke, so
        // neighbouring ramp steps read apart.
        return (
          <Bar
            key={s.key}
            {...common}
            fill={colors[i]}
            maxBarSize={32}
            {...(stacked
              ? {
                  stackId: `stack-${axis}`,
                  stroke: "var(--card)",
                  strokeWidth: 1,
                }
              : { radius: [2, 2, 0, 0] as [number, number, number, number] })}
          >
            {kept.has(i) ? (
              <LabelList
                dataKey={s.key}
                content={barMarker(colors[i], kept.get(i) ?? new Map())}
              />
            ) : null}
          </Bar>
        );
    }
  });

  const markerMarks = bars
    ? []
    : [...kept].map(([seriesIndex, labels]) => (
        <Line
          key={markerKey(seriesIndex)}
          dataKey={markerKey(seriesIndex)}
          yAxisId={series[seriesIndex].axis ?? "left"}
          stroke="none"
          legendType="none"
          tooltipType="none"
          isAnimationActive={false}
          activeDot={false}
          dot={markerDot(colors[seriesIndex], labels)}
        />
      ));

  const chart = (
    <ComposedChart
      data={rows}
      margin={MARGIN}
      width={width}
      height={width === undefined ? undefined : height}
      aria-label={title}
      aria-describedby={summaryId}
      barCategoryGap="20%"
    >
      {grid ? (
        <CartesianGrid vertical={false} stroke="var(--border)" yAxisId="left" />
      ) : null}
      <XAxis
        dataKey={xKey}
        tickFormatter={(value: string | number) => xFormat(value)}
        tick={AXIS_TICK}
        axisLine={false}
        tickLine={false}
        minTickGap={16}
      />
      <YAxis
        yAxisId="left"
        tickFormatter={(value: number) => axisFormat(value)}
        tick={AXIS_TICK}
        axisLine={false}
        tickLine={false}
        width={40}
      />
      {hasRight ? (
        <YAxis
          yAxisId="right"
          orientation="right"
          tickFormatter={(value: number) => rightAxisFormat(value)}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          width={40}
        />
      ) : null}
      <Tooltip
        cursor={
          kind === "bar" || kind === "stacked-bar"
            ? { fill: "var(--muted)" }
            : { stroke: "var(--border)" }
        }
        isAnimationActive={false}
        // Keep gap entries, so a category where every series is a gap still
        // shows its tooltip (Recharts hides one with an empty payload).
        filterNull={false}
        content={<ChartTooltip series={tooltipSeries} fmt={fmt} />}
      />
      {marks}
      {markerMarks}
    </ComposedChart>
  );

  return (
    <ChartFrame
      slot={slot}
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
      legend={
        legend === "none"
          ? undefined
          : {
              position: legend,
              items: series.map((s, i) => ({
                key: s.key,
                label: s.label,
                color: colors[i],
              })),
            }
      }
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
