import { expect, it } from "vitest";
import {
  describeChart,
  type Formatters,
  formatAxisValue,
  formatValue,
  numberAt,
  tableRows,
} from "./describe";
import { markerKey, planMarkers } from "./markers";

const fmt: Formatters = { value: formatValue, x: String };
const data = [
  { day: "9 Aug", pages: 10, cost: 0.5 },
  { day: "10 Aug", pages: 2981, cost: null },
  { day: "11 Aug", pages: 20, cost: 1.25 },
];

it("formats values grouped and axis ticks compact", () => {
  expect(formatValue(2981)).toBe("2,981");
  expect(formatAxisValue(2300)).toBe("2.3K");
  expect(formatAxisValue(750)).toBe("750");
});

it("reads only finite numbers; anything else is a gap", () => {
  expect(numberAt({ v: 3 }, "v")).toBe(3);
  expect(numberAt({ v: null }, "v")).toBeNull();
  expect(numberAt({ v: "3" }, "v")).toBeNull();
  expect(numberAt({ v: Number.NaN }, "v")).toBeNull();
  expect(numberAt({}, "v")).toBeNull();
});

it("summarises the range and each series' extremes, skipping gaps and using the series format", () => {
  expect(
    describeChart({
      kind: "line",
      title: "Throughput",
      data,
      xKey: "day",
      series: [
        { key: "pages", label: "Pages" },
        { key: "cost", label: "Cost", format: (v) => `$${v.toFixed(2)}` },
      ],
      markers: [
        { index: 1, series: "pages", label: "10 Aug · 2,981 pages" },
        { index: 9, series: "pages", label: "out of range" },
      ],
      fmt,
    }),
  ).toBe(
    "Throughput. Line chart, 3 points from 9 Aug to 11 Aug. " +
      "Pages: highest 2,981 at 10 Aug, lowest 10 at 9 Aug. " +
      "Cost: highest $1.25 at 11 Aug, lowest $0.50 at 9 Aug. " +
      "Marked: 10 Aug · 2,981 pages.",
  );
});

it("says so when there is one point, or a series has no values", () => {
  expect(
    describeChart({
      kind: "stacked-bar",
      title: "Pages by mode",
      data: [{ day: "1 Sep", a: null }],
      xKey: "day",
      series: [{ key: "a", label: "Native" }],
      fmt: { value: formatValue, x: (x) => `on ${x}` },
    }),
  ).toBe(
    "Pages by mode. Stacked bar chart, 1 point, on 1 Sep. Native: no values.",
  );
});

it("builds one table row per datum, a dash for a gap", () => {
  expect(
    tableRows(
      data,
      "day",
      [
        { key: "pages", label: "Pages" },
        { key: "cost", label: "Cost" },
      ],
      fmt,
    ),
  ).toEqual([
    ["9 Aug", "10", "0.5"],
    ["10 Aug", "2,981", "–"],
    ["11 Aug", "20", "1.25"],
  ]);
});

it("plans markers by row index and ignores unknown series and rows", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const plan = planMarkers(
    data,
    series,
    [
      { index: 1, series: "pages", label: "peak" },
      { index: 1, series: "cost", label: "gap" }, // no value: no dot
      { index: -1, series: "pages", label: "neg" },
      { index: 1.5, series: "pages", label: "frac" },
      // @ts-expect-error an unknown series is ignored at runtime too
      { index: 0, series: "nope", label: "unknown" },
    ],
    false,
  );
  expect(plan.rows.map((r) => r[markerKey(0)])).toEqual([null, 2981, null]);
  expect(plan.rows.map((r) => r[markerKey(1)])).toEqual([null, null, null]);
  expect(plan.series.map((s) => [s.seriesIndex, [...s.labels]])).toEqual([
    [0, [[1, "peak"]]],
    [1, [[1, "gap"]]],
  ]);
});

it("returns the data untouched when nothing is marked", () => {
  const plan = planMarkers(data, [{ key: "pages", label: "P" }], [], false);
  expect(plan.rows).toBe(data);
  expect(plan.series).toEqual([]);
});

it("in a stacked chart puts a marker on top of its segment, counting only its own axis' stack", () => {
  const rows = [{ x: "a", low: 2, high: 5, other: 100 }];
  const plan = planMarkers(
    rows,
    [
      { key: "low", label: "Low" },
      { key: "other", label: "Other", axis: "right" },
      { key: "high", label: "High" },
    ],
    [{ index: 0, series: "high", label: "top" }],
    true,
  );
  expect(plan.rows[0][markerKey(2)]).toBe(7);
});
