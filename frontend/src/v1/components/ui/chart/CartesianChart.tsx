import { type JSX, useEffect, useId, useMemo, useState } from "react";
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
  hasValues,
  tableRows,
  unparsedWarnings,
} from "./describe";
import {
  chartRows,
  droppedWarnings,
  keptLabels,
  keptMarkers,
  markerKey,
  markerLabelKey,
  reservedKeyWarnings,
} from "./markers";
import { BarMarker, isolatedDot, markerDot } from "./marks";
import { seriesColors } from "./palette";
import type { CartesianChartProps, ChartDatum } from "./types";

export const DEFAULT_CHART_HEIGHT = 240;

const NO_MARKERS: readonly never[] = [];

const AXIS_TICK = { fill: "var(--muted-foreground)" };
// Room for a marker label above the highest point.
const MARGIN = { top: 20, right: 8, bottom: 0, left: 0 };
const Y_AXIS_WIDTH = 40;

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
  // The active point's sentence, for the live region (see ChartTooltip).
  const [live, setLive] = useState("");
  const fmt: Formatters = { value: valueFormat, x: xFormat };
  const colors = seriesColors(series);
  const stacked = kind === "stacked-bar";
  const bars = kind === "bar" || stacked;
  const resolved =
    state === "ready" && !hasValues(data, series) ? "empty" : state;
  // Recharts resets its data store whenever the rows it gets change
  // identity, so the rows are `data` itself unless something is marked, and
  // are memoised on what the series and markers say rather than on their
  // identity: pages pass both as inline literals, new on every render.
  const seriesKeys = series.map((s) => s.key).join("\n");
  const markerSpec = markers
    .map((m) => `${m.index}\t${m.series}\t${m.label}`)
    .join("\n");
  // biome-ignore lint/correctness/useExhaustiveDependencies: keyed on the content of series and markers (seriesKeys, markerSpec), not their identity.
  const { kept, dropped } = useMemo(
    () => keptMarkers(data, series, markers),
    [data, seriesKeys, markerSpec],
  );
  // biome-ignore lint/correctness/useExhaustiveDependencies: series only matters through its keys, and kept changes whenever they do.
  const rows = useMemo(
    () => chartRows(data, series, kept, bars),
    [data, kept, bars],
  );
  // Logged whenever the set of problems changes (and, as with every effect,
  // twice on mount under StrictMode in development). A reserved series key
  // or an unparsed value is a mistake in any state (the latter is why a
  // chart with data may show its empty state); a dropped marker only while
  // showing data, since a marker computed for rows still loading is not one.
  const warnings = JSON.stringify([
    ...reservedKeyWarnings(series),
    ...unparsedWarnings(data, series),
    ...(resolved === "ready" ? droppedWarnings(dropped) : []),
  ]);
  useEffect(() => {
    for (const warning of JSON.parse(warnings) as string[]) {
      console.warn(warning);
    }
  }, [warnings]);
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
            dot={isolatedDot(colors[i])}
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
            dot={isolatedDot(colors[i])}
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
                dataKey={markerLabelKey(s.key)}
                content={<BarMarker color={colors[i]} />}
              />
            ) : null}
          </Bar>
        );
    }
  });

  const markerMarks = bars
    ? []
    : [...kept.keys()].map((seriesIndex) => (
        <Line
          key={markerKey(series[seriesIndex].key)}
          dataKey={markerKey(series[seriesIndex].key)}
          yAxisId={series[seriesIndex].axis ?? "left"}
          stroke="none"
          legendType="none"
          tooltipType="none"
          isAnimationActive={false}
          activeDot={false}
          dot={markerDot(
            colors[seriesIndex],
            markerLabelKey(series[seriesIndex].key),
          )}
        />
      ));

  const chart = (
    <ComposedChart
      data={rows as ChartDatum[]}
      margin={MARGIN}
      width={width}
      height={width === undefined ? undefined : height}
      aria-label={title}
      aria-describedby={summaryId}
      barCategoryGap="20%"
      // Positives stack up from zero and negatives down, so a mixed-sign
      // stack (credits and refunds) is not drawn inside its positive segment.
      {...(stacked ? { stackOffset: "sign" } : {})}
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
        width={Y_AXIS_WIDTH}
      />
      {hasRight ? (
        <YAxis
          yAxisId="right"
          orientation="right"
          tickFormatter={(value: number) => rightAxisFormat(value)}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          width={Y_AXIS_WIDTH}
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
        content={
          <ChartTooltip series={tooltipSeries} fmt={fmt} onAnnounce={setLive} />
        }
      />
      {marks}
      {markerMarks}
    </ComposedChart>
  );

  return (
    <ChartFrame
      slot={slot}
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
