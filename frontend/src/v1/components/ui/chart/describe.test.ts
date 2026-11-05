import { expect, it } from "vitest";
import {
  describeChart,
  type Formatters,
  formatAxisValue,
  formatValue,
  numberAt,
  tableRows,
} from "./describe";
import { keptLabels, keptMarkers, markerKey, markerRows } from "./markers";

const fmt: Formatters = { value: formatValue, x: String };
type Row = { day: string; pages: number; cost: number | null };
const data: Row[] = [
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
      markerLabels: ["10 Aug · 2,981 pages"],
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

it("keeps only markers that will be drawn: a charted series, an integer row in range, a value there", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const kept = keptMarkers<Row>(data, series, [
    { index: 2, series: "pages", label: "late" },
    { index: 0, series: "pages", label: "early" },
    { index: 1, series: "cost", label: "gap" }, // cost is null on row 1
    { index: 0, series: "cost", label: "cost" },
    { index: -1, series: "pages", label: "negative" },
    { index: 3, series: "pages", label: "past the end" },
    { index: 1.5, series: "pages", label: "fractional" },
  ]);
  expect([...kept].map(([s, byRow]) => [s, [...byRow]])).toEqual([
    [
      0,
      [
        [2, "late"],
        [0, "early"],
      ],
    ],
    [1, [[0, "cost"]]],
  ]);
  // The summary reads the same set, in series then row order.
  expect(keptLabels(kept)).toEqual(["early", "late", "cost"]);
});

it("drops a marker on a series that is not charted", () => {
  expect(
    keptMarkers<Row>(
      data,
      [{ key: "pages", label: "Pages" }],
      [{ index: 0, series: "cost", label: "not charted" }],
    ).size,
  ).toBe(0);
});

it("adds one marker field per marked series to line and area rows", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const kept = keptMarkers<Row>(data, series, [
    { index: 1, series: "pages", label: "peak" },
  ]);
  const rows = markerRows(data, series, kept) as Record<string, unknown>[];
  expect(rows.map((r) => r[markerKey(0)])).toEqual([null, 2981, null]);
  expect(rows.map((r) => markerKey(1) in r)).toEqual([false, false, false]);
  expect(rows[1]).toMatchObject(data[1]);
});

it("returns the data untouched when nothing is marked", () => {
  expect(markerRows(data, [{ key: "pages", label: "P" }], new Map())).toBe(
    data,
  );
});
