import { expect, it } from "vitest";
import {
  describeChart,
  type Formatters,
  hasValues,
  numberAt,
  numberFormats,
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
import type {
  CategoryKey,
  ChartMarker,
  ChartSeries,
  NumericKey,
} from "./types";

// A fixed locale, so expectations hold on any machine; the components default
// to the viewer's.
const EN = numberFormats("en-US");
const fmt: Formatters = { value: EN.value, x: String };
type Row = { day: string; pages: number; cost: number | null };
const data: Row[] = [
  { day: "9 Aug", pages: 10, cost: 0.5 },
  { day: "10 Aug", pages: 2981, cost: null },
  { day: "11 Aug", pages: 20, cost: 1.25 },
];

it("formats values grouped and axis ticks compact, in the locale given", () => {
  expect(EN.value(2981)).toBe("2,981");
  expect(EN.axis(2300)).toBe("2.3K");
  expect(EN.axis(750)).toBe("750");
  expect(numberFormats("de-DE").value(2981)).toBe("2.981");
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
      fmt: { value: EN.value, x: (x) => `on ${x}` },
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

it("keeps only markers that will be drawn: a charted series, an integer row in range, a value there, the first per point", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const { kept, dropped } = keptMarkers<Row>(data, series, [
    { index: 2, series: "pages", label: "late" },
    { index: 0, series: "pages", label: "early" },
    { index: 1, series: "cost", label: "gap" }, // cost is null on row 1
    { index: 0, series: "cost", label: "cost" },
    { index: -1, series: "pages", label: "negative" },
    { index: 3, series: "pages", label: "past the end" },
    { index: 1.5, series: "pages", label: "fractional" },
    { index: 2, series: "pages", label: "second on row 2" },
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
  expect(dropped).toEqual([
    { label: "gap", reason: "the series has no value on that row" },
    { label: "negative", reason: "row -1 is not a row of data (3 rows)" },
    { label: "past the end", reason: "row 3 is not a row of data (3 rows)" },
    { label: "fractional", reason: "row 1.5 is not a row of data (3 rows)" },
    {
      label: "second on row 2",
      reason: "an earlier marker already labels that point",
    },
  ]);
});

it("drops a marker on a series that is not charted", () => {
  expect(
    keptMarkers<Row>(
      data,
      [{ key: "pages", label: "Pages" }],
      [{ index: 0, series: "cost", label: "not charted" }],
    ),
  ).toEqual({
    kept: new Map(),
    dropped: [{ label: "not charted", reason: "its series is not charted" }],
  });
});

it("words a warning per dropped marker and per reserved series key", () => {
  expect(
    reservedKeyWarnings([
      { key: "pages", label: "Pages" },
      { key: "__marker_x", label: "Clash" },
    ]),
  ).toEqual([
    'Chart series key "__marker_x" starts with "__marker", which the chart uses for markers; rename the field.',
  ]);
  expect(
    droppedWarnings([{ label: "A", reason: "its series is not charted" }]),
  ).toEqual(['Chart marker "A" not drawn: its series is not charted.']);
});

it("draws no markers when a series key is reserved, since marker fields could overwrite it", () => {
  type Pivot = Record<string, number>;
  const rows: Pivot[] = [{ a: 1, __marker_x: 2 }];
  expect(
    keptMarkers<Pivot>(
      rows,
      [
        { key: "a", label: "A" },
        { key: "__marker_x", label: "X" },
      ],
      [{ index: 0, series: "a", label: "peak" }],
    ),
  ).toEqual({
    kept: new Map(),
    dropped: [
      {
        label: "peak",
        reason: 'a series key starts with "__marker", which markers reserve',
      },
    ],
  });
});

it("orders the summary's markers by series, then row, whatever order they were given in", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const { kept } = keptMarkers<Row>(data, series, [
    { index: 0, series: "cost", label: "cost first given" },
    { index: 2, series: "pages", label: "pages late" },
    { index: 0, series: "pages", label: "pages early" },
  ]);
  expect(keptLabels(kept)).toEqual([
    "pages early",
    "pages late",
    "cost first given",
  ]);
});

it("returns the data itself when nothing is marked", () => {
  const series = [{ key: "pages", label: "P" }] as const;
  expect(chartRows(data, series, new Map(), false)).toBe(data);
  expect(chartRows(data, series, new Map(), true)).toBe(data);
});

it("carries each marker's value (line and area) and label in its own row", () => {
  const series = [
    { key: "pages", label: "Pages" },
    { key: "cost", label: "Cost" },
  ] as const;
  const { kept } = keptMarkers<Row>(data, series, [
    { index: 1, series: "pages", label: "peak" },
  ]);
  const line = chartRows(data, series, kept, false) as Record<
    string,
    unknown
  >[];
  expect(line.map((r) => r[markerKey("pages")])).toEqual([null, 2981, null]);
  expect(line.map((r) => r[markerLabelKey("pages")])).toEqual([
    undefined,
    "peak",
    undefined,
  ]);
  expect(line.map((r) => markerKey("cost") in r)).toEqual([
    false,
    false,
    false,
  ]);
  expect(line[1]).toMatchObject(data[1]);
  // Named by series key, so a series keeps its own fields if another is
  // removed or reordered.
  expect(Object.keys(line[1])).toEqual(
    expect.arrayContaining(["__marker:pages", "__marker_label:pages"]),
  );
  // Bars read only the label: the bar itself is the point.
  const bars = chartRows(data, series, kept, true) as Record<string, unknown>[];
  expect(bars.map((r) => r[markerLabelKey("pages")])).toEqual([
    undefined,
    "peak",
    undefined,
  ]);
  expect(bars.map((r) => markerKey("pages") in r)).toEqual([
    false,
    false,
    false,
  ]);
});

/*
 * The key types are the contract other pages build against; these lines are
 * checked by `typecheck:v1` (test files are in the v1 tsconfig), so loosening
 * a key type fails the typecheck.
 */
it("types series, marker and category keys by what their field holds", () => {
  interface ApiRow {
    day: string;
    pages: number;
    failed?: number | null;
    cost: string; // a DRF Decimal, still a string
    at: Date;
  }
  const rows: ApiRow[] = [];
  const ok: ChartSeries<ApiRow>[] = [
    { key: "pages", label: "Pages" },
    { key: "failed", label: "Failed" },
  ];
  // @ts-expect-error a numeric string must be parsed before charting
  const stringSeries: ChartSeries<ApiRow> = { key: "cost", label: "Cost" };
  // @ts-expect-error not a field of the row
  const unknownSeries: ChartSeries<ApiRow> = { key: "nope", label: "Nope" };
  // @ts-expect-error the category must be a string or a number
  const dateCategory: CategoryKey<ApiRow> = "at";
  const marker: ChartMarker<ApiRow> = {
    index: 0,
    series: "pages",
    label: "peak",
  };
  // @ts-expect-error markers sit on numeric series only
  const stringMarker: ChartMarker<ApiRow> = { ...marker, series: "day" };
  // Pivoted rows, one field per dynamic series, cannot be checked per key.
  const pivoted: NumericKey<Record<string, string | number>> = "model-a";
  const pivotedCategory: CategoryKey<Record<string, string | number | null>> =
    "day";
  // @ts-expect-error an index that can never hold a number has no series key
  const allStrings: NumericKey<Record<string, string>> = "cost";
  // An index that can only hold numbers, however narrowly, has any key.
  const flags: NumericKey<Record<string, 0 | 1>> = "on";
  // Loosely typed JSON rows: nothing is known, so nothing is refused.
  const looseSeries: NumericKey<Record<string, unknown>> = "pages";
  const looseCategory: CategoryKey<Record<string, unknown> & { day: string }> =
    "day";
  // @ts-expect-error an index of objects has no category key
  const objectCategory: CategoryKey<Record<string, { n: number }>> = "x";
  // @ts-expect-error an untyped `[]` infers never, which accepts no key
  const fromEmpty: NumericKey<never> = "pages";
  // @ts-expect-error likewise for the category
  const categoryFromEmpty: CategoryKey<never> = "day";
  expect([
    rows,
    ok,
    stringSeries,
    unknownSeries,
    dateCategory,
    stringMarker,
    pivoted,
    pivotedCategory,
    allStrings,
    objectCategory,
    fromEmpty,
    categoryFromEmpty,
    flags,
    looseSeries,
    looseCategory,
  ]).toHaveLength(15);
});

it("finds values only in the series' own keys, and reads null, missing, non-finite and strings as gaps", () => {
  const pages = [{ key: "pages" }];
  // A numeric category or extra column is not a series value.
  expect(hasValues([{ t: 1, other: 5, pages: null }], pages)).toBe(false);
  expect(hasValues([{ t: 1 }], pages)).toBe(false);
  expect(hasValues([{ pages: Number.NaN }], pages)).toBe(false);
  expect(hasValues([{ pages: 0 }], pages)).toBe(true);
  // An unparsed numeric string is a gap, as everywhere else in the chart.
  expect(hasValues([{ pages: "12.5" }], pages)).toBe(false);
  expect(hasValues([{ pages: 3 }], [])).toBe(false);
  expect(hasValues([], pages)).toBe(false);
});

it("warns once per series that holds a value that is not a number, and never for gaps", () => {
  const series = [{ key: "pages" }, { key: "cost" }, { key: "failed" }];
  expect(
    unparsedWarnings(
      [
        { pages: "1", cost: 2, failed: null },
        { pages: "3", cost: undefined, failed: Number.NaN },
      ],
      series,
    ),
  ).toEqual([
    'Chart series "pages" has values that are not numbers; the chart reads them as gaps. Parse numeric strings before passing them.',
  ]);
});
