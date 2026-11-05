import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { THEME_MODES } from "@v1/lib/theme";
import { installResizeObserver, renderV1 } from "@v1/test";
import type { JSX } from "react";
import { describe, expect, it, vi } from "vitest";
import {
  AreaChart,
  BarChart,
  type CartesianChartProps,
  LineChart,
  numberFormats,
  Sparkline,
  StackedBarChart,
} from "./index";

// A fixed locale, so "2,981" holds on any machine; the charts default to the
// viewer's.
const EN = numberFormats("en-US");

const WIDTH = 400;
const HEIGHT = 200;

const data = [
  { day: "9 Aug", pages: 10, failed: 1 },
  { day: "10 Aug", pages: 2981, failed: 600 },
  { day: "11 Aug", pages: 20, failed: 2 },
];
type Row = (typeof data)[number];

const SERIES = [
  { key: "pages", label: "Pages processed" },
  { key: "failed", label: "Failed pages" },
] as const;

const VARIANTS: [string, (p: CartesianChartProps<Row>) => JSX.Element][] = [
  ["line-chart", (p) => <LineChart {...p} />],
  ["area-chart", (p) => <AreaChart {...p} />],
  ["bar-chart", (p) => <BarChart {...p} />],
  ["stacked-bar-chart", (p) => <StackedBarChart {...p} />],
];

function props(
  overrides: Partial<CartesianChartProps<Row>> = {},
): CartesianChartProps<Row> {
  return {
    title: "Throughput",
    data,
    xKey: "day",
    xLabel: "Day",
    series: SERIES,
    width: WIDTH,
    height: HEIGHT,
    valueFormat: EN.value,
    axisFormat: EN.axis,
    ...overrides,
  };
}

/**
 * Recharts maps the pointer to a category from the wrapper's bounding box and
 * its offset size, which happy-dom reports as zero. Stubs both to the chart's
 * size so a mouse move lands where the test says. (Undone after each test by
 * `restoreMocks`.) A candidate for the shared harness if other charts need it.
 */
function stubLayout(): void {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue(
    new DOMRect(0, 0, WIDTH, HEIGHT),
  );
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(WIDTH);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(
    HEIGHT,
  );
}

function plot(container: HTMLElement): SVGSVGElement {
  const svg = container.querySelector<SVGSVGElement>("svg.recharts-surface");
  if (svg === null) {
    throw new Error("no chart surface");
  }
  return svg;
}

describe.each(VARIANTS)("%s", (slot, Chart) => {
  it("colours untoned series from the ramp in order and toned ones from their token", () => {
    const { container } = renderV1(
      <Chart
        {...props({
          series: [
            { key: "pages", label: "Pages processed" },
            { key: "failed", label: "Failed pages", tone: "destructive" },
          ],
        })}
      />,
    );
    const root = container.querySelector(`[data-slot=${slot}]`);
    expect(root).toHaveAttribute("data-state", "ready");
    const attr = slot.includes("bar") ? "fill" : "stroke";
    // An area's fill path has no stroke; its curve carries the colour.
    const paint = (name: string) =>
      new Set(
        [...container.querySelectorAll(`[name="${name}"]`)]
          .map((el) => el.getAttribute(attr))
          .filter((value) => value !== "none"),
      );
    expect(paint("Pages processed")).toEqual(new Set(["var(--chart-1)"]));
    expect(paint("Failed pages")).toEqual(new Set(["var(--destructive)"]));
  });

  it("lists every series in the legend, below the plot by default", () => {
    const { container } = renderV1(<Chart {...props()} />);
    const legend = container.querySelector("[data-slot=chart-legend]");
    expect(legend).not.toBeNull();
    expect(
      within(legend as HTMLElement)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Pages processed", "Failed pages"]);
    expect(
      plot(container).compareDocumentPosition(legend as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("names the plot, points it at the summary and carries every value in a table", async () => {
    const { container } = renderV1(<Chart {...props()} />);
    const svg = plot(container);
    expect(svg).toHaveAttribute("aria-label", "Throughput");
    const summary = document.getElementById(
      svg.getAttribute("aria-describedby") ?? "",
    );
    expect(summary).toHaveTextContent(
      /^Throughput\. .* chart, 3 points from 9 Aug to 11 Aug\. Pages processed: highest 2,981 at 10 Aug/,
    );
    const table = screen.getByRole("table", { name: "Throughput" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((c) => c.textContent),
    ).toEqual(["Day", "Pages processed", "Failed pages"]);
    expect(
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((r) => r.textContent),
    ).toEqual(["9 Aug101", "10 Aug2,981600", "11 Aug202"]);
    await expect(container).toHaveNoA11yViolations();
  });

  it("shows the tooltip on hover", async () => {
    stubLayout();
    const { container } = renderV1(<Chart {...props()} />);
    const wrapper = container.querySelector(".recharts-wrapper");
    // The middle of the plot is the second category.
    fireEvent.mouseMove(wrapper as Element, {
      clientX: WIDTH / 2,
      clientY: 100,
    });
    // Recharts handles the move on the next animation frame.
    await waitFor(() =>
      expect(
        container.querySelector("[data-slot=chart-tooltip]"),
      ).toHaveTextContent("10 AugPages processed2,981Failed pages600"),
    );
  });

  it("moves the tooltip with the arrow keys once the plot has focus", async () => {
    const { container, user } = renderV1(<Chart {...props()} />);
    const svg = plot(container);
    expect(svg).toHaveAttribute("tabindex", "0");
    await user.tab();
    expect(svg).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    const tooltip = () => container.querySelector("[data-slot=chart-tooltip]");
    expect(tooltip()).toHaveTextContent(/^10 Aug/);
    await user.keyboard("{ArrowRight}");
    expect(tooltip()).toHaveTextContent(/^11 Aug/);
    await user.keyboard("{ArrowLeft}");
    expect(tooltip()).toHaveTextContent(/^10 Aug/);
  });

  it("draws markers as a dot series, labelled, and never as a reference line or dot", () => {
    const { container } = renderV1(
      <Chart
        {...props({
          markers: [
            { index: 1, series: "pages", label: "10 Aug · 2,981 pages" },
          ],
        })}
      />,
    );
    const markers = container.querySelectorAll("[data-slot=chart-marker]");
    expect(markers).toHaveLength(1);
    expect(markers[0]).toHaveTextContent("10 Aug · 2,981 pages");
    expect(
      container.querySelector(
        ".recharts-reference-line, .recharts-reference-dot, .recharts-reference-area",
      ),
    ).toBeNull();
    expect(
      screen.getByText(/Marked: 10 Aug · 2,981 pages\./),
    ).toBeInTheDocument();
  });

  it("shows a skeleton sized to the chart while loading, and no plot", () => {
    const { container } = renderV1(<Chart {...props({ state: "loading" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading Throughput");
    expect(container.querySelector("[data-slot=skeleton-block]")).toHaveClass(
      "ui:h-(--chart-height)",
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelector(`[data-slot=${slot}]`)).toHaveStyle({
      "--chart-height": "200px",
    });
  });

  it("shows the empty message when there are no rows, or the slot when given", () => {
    const { container, rerender } = renderV1(
      <Chart {...props({ data: [] })} />,
    );
    expect(container.querySelector(`[data-slot=${slot}]`)).toHaveAttribute(
      "data-state",
      "empty",
    );
    expect(screen.getByText("No data for this period")).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();
    rerender(
      <Chart
        {...props({ state: "empty", emptySlot: <p>Nothing extracted yet</p> })}
      />,
    );
    expect(screen.getByText("Nothing extracted yet")).toBeInTheDocument();
    expect(screen.queryByText("No data for this period")).toBeNull();
  });
});

describe("cartesian options", () => {
  it("puts the legend above the plot, or hides it", () => {
    const { container, rerender } = renderV1(
      <LineChart {...props({ legend: "top" })} />,
    );
    const legend = container.querySelector("[data-slot=chart-legend]");
    expect(
      plot(container).compareDocumentPosition(legend as Node) &
        Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
    rerender(<LineChart {...props({ legend: "none" })} />);
    expect(container.querySelector("[data-slot=chart-legend]")).toBeNull();
  });

  it("uses a caller's summary, formats and empty message", () => {
    renderV1(
      <LineChart
        {...props({
          summary: "10 Aug carries most of the month.",
          valueFormat: (v) => `${v} pg`,
          xFormat: (x) => `day ${x}`,
          axisFormat: (v) => `${v}!`,
        })}
      />,
    );
    expect(
      screen.getByText("10 Aug carries most of the month."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("rowheader", { name: "day 10 Aug" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "2981 pg" })).toBeInTheDocument();
    expect(screen.getAllByText(/!$/).length).toBeGreaterThan(0);
  });

  it("draws a right axis only when a series asks for it", () => {
    const { container, rerender } = renderV1(<LineChart {...props()} />);
    expect(container.querySelectorAll(".recharts-yAxis")).toHaveLength(1);
    rerender(
      <LineChart
        {...props({
          series: [
            { key: "pages", label: "Pages" },
            {
              key: "failed",
              label: "Cost",
              axis: "right",
              format: (v) => `$${v}`,
            },
          ],
        })}
      />,
    );
    expect(container.querySelectorAll(".recharts-yAxis")).toHaveLength(2);
    expect(screen.getByRole("cell", { name: "$600" })).toBeInTheDocument();
  });

  it("keeps a marker on the row it names when category labels repeat", () => {
    const weeks = [
      { day: "Mon", pages: 1, failed: 0 },
      { day: "Tue", pages: 2, failed: 0 },
      { day: "Mon", pages: 9, failed: 0 },
    ];
    const { container } = renderV1(
      <LineChart
        {...props({
          data: weeks,
          markers: [{ index: 2, series: "pages", label: "second Monday" }],
        })}
      />,
    );
    const marker = container.querySelector("[data-slot=chart-marker] circle");
    const curve = container
      .querySelector(`.recharts-line-curve[name="Pages processed"]`)
      ?.getAttribute("d");
    // The curve's last vertex is the third row; the marker sits on it.
    const last = curve?.split("L").at(-1)?.split(",").map(Number);
    expect([
      Number(marker?.getAttribute("cx")),
      Number(marker?.getAttribute("cy")),
    ]).toEqual(last);
  });

  it("puts a bar marker over its own bar in a group, and on top of its own segment in a stack", () => {
    const geometry = (el: Element | null | undefined) => ({
      x: Number(el?.getAttribute("x")),
      y: Number(el?.getAttribute("y")),
      width: Number(el?.getAttribute("width")),
    });
    const markerAt = (container: HTMLElement) => {
      const circle = container.querySelector("[data-slot=chart-marker] circle");
      return {
        cx: Number(circle?.getAttribute("cx")),
        cy: Number(circle?.getAttribute("cy")),
      };
    };
    const marker = [{ index: 1, series: "pages", label: "peak" }] as const;
    // Grouped: "pages" is the first of two bars in row 1.
    const grouped = renderV1(<BarChart {...props({ markers: marker })} />);
    const bar = geometry(
      grouped.container.querySelectorAll(`path[name="Pages processed"]`)[1],
    );
    expect(markerAt(grouped.container).cx).toBeCloseTo(bar.x + bar.width / 2);
    expect(markerAt(grouped.container).cy).toBeCloseTo(bar.y);
    grouped.unmount();
    // Stacked: "pages" is the bottom segment, with "failed" above it.
    const stacked = renderV1(
      <StackedBarChart {...props({ markers: marker })} />,
    );
    const segment = geometry(
      stacked.container.querySelectorAll(`path[name="Pages processed"]`)[1],
    );
    const above = geometry(
      stacked.container.querySelectorAll(`path[name="Failed pages"]`)[1],
    );
    expect(above.y).toBeLessThan(segment.y);
    expect(markerAt(stacked.container).cx).toBeCloseTo(
      segment.x + segment.width / 2,
    );
    expect(markerAt(stacked.container).cy).toBeCloseTo(segment.y);
  });

  it("keeps a bar marker on its row when earlier rows are gaps, which draw no bar", () => {
    const gappy = [
      { day: "1", pages: 10 as number | null },
      { day: "2", pages: null },
      { day: "3", pages: 30 },
      { day: "4", pages: 40 },
    ];
    const { container } = renderV1(
      <BarChart
        title="T"
        data={gappy}
        xKey="day"
        width={WIDTH}
        height={HEIGHT}
        series={[{ key: "pages", label: "Pages" }]}
        markers={[
          { index: 2, series: "pages", label: "third" },
          { index: 3, series: "pages", label: "last" },
        ]}
      />,
    );
    // Bars drawn: rows 1, 3 and 4 (the gap draws none).
    const bars = [...container.querySelectorAll(`path[name="Pages"]`)].map(
      (el) => ({
        centre:
          Number(el.getAttribute("x")) + Number(el.getAttribute("width")) / 2,
        top: Number(el.getAttribute("y")),
      }),
    );
    expect(bars).toHaveLength(3);
    const marks = [...container.querySelectorAll("[data-slot=chart-marker]")];
    expect(marks.map((m) => m.textContent)).toEqual(["third", "last"]);
    const at = (m: Element) => {
      const circle = m.querySelector("circle");
      return {
        centre: Number(circle?.getAttribute("cx")),
        top: Number(circle?.getAttribute("cy")),
      };
    };
    expect(at(marks[0]).centre).toBeCloseTo(bars[1].centre);
    expect(at(marks[0]).top).toBeCloseTo(bars[1].top);
    expect(at(marks[1]).centre).toBeCloseTo(bars[2].centre);
    expect(at(marks[1]).top).toBeCloseTo(bars[2].top);
  });

  it("stacks right-axis series separately, beside the left stack and from their own baseline", () => {
    const { container } = renderV1(
      <StackedBarChart
        {...props({
          series: [
            { key: "pages", label: "Pages processed" },
            { key: "failed", label: "Failed pages", axis: "right" },
          ],
        })}
      />,
    );
    const bottom = (el: Element | undefined) =>
      Number(el?.getAttribute("y")) + Number(el?.getAttribute("height"));
    const left = container.querySelectorAll(`path[name="Pages processed"]`);
    const right = container.querySelectorAll(`path[name="Failed pages"]`);
    // Row 1: the right-axis bar starts at the plot's baseline, not on top of
    // the left-axis bar.
    expect(bottom(right[1])).toBeCloseTo(bottom(left[1]));
    // ...and beside it, not drawn over it (one shared stack would overlap).
    expect(Number(right[1]?.getAttribute("x"))).toBeGreaterThanOrEqual(
      Number(left[1]?.getAttribute("x")) +
        Number(left[1]?.getAttribute("width")),
    );
  });

  it("colours a marker as its series, and keeps marker series out of the tooltip", async () => {
    const { container, user } = renderV1(
      <LineChart
        {...props({
          series: [
            { key: "pages", label: "Pages processed" },
            { key: "failed", label: "Failed pages", tone: "destructive" },
          ],
          markers: [{ index: 1, series: "failed", label: "spike" }],
        })}
      />,
    );
    expect(
      container.querySelector("[data-slot=chart-marker] circle"),
    ).toHaveAttribute("fill", "var(--destructive)");
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(
      container.querySelector("[data-slot=chart-tooltip]"),
    ).toHaveTextContent(/^10 AugPages processed2,981Failed pages600$/);
  });

  it("neither draws nor reads out a marker on a gap or an uncharted series", () => {
    const gappy = [
      { day: "9 Aug", pages: 10, failed: 1 },
      { day: "10 Aug", pages: null, failed: 600 },
    ];
    const { container } = renderV1(
      <LineChart
        title="Throughput"
        data={gappy}
        xKey="day"
        width={WIDTH}
        height={HEIGHT}
        series={[{ key: "pages", label: "Pages" }]}
        markers={[
          { index: 1, series: "pages", label: "on a gap" },
          { index: 1, series: "failed", label: "not charted" },
        ]}
      />,
    );
    expect(container.querySelector("[data-slot=chart-marker]")).toBeNull();
    expect(screen.queryByText(/Marked:/)).toBeNull();
  });

  it("draws a point with no neighbour as a dot, and leaves connected points to the line", () => {
    const rows = [
      { day: "1", pages: 5, failed: 1 },
      { day: "2", pages: null, failed: 2 },
      { day: "3", pages: 7, failed: 3 },
      { day: "4", pages: 8, failed: null },
    ];
    for (const Chart of [LineChart, AreaChart]) {
      const { container, unmount } = renderV1(
        <Chart
          title="T"
          data={rows}
          xKey="day"
          width={WIDTH}
          height={HEIGHT}
          series={[
            { key: "pages", label: "Pages" },
            { key: "failed", label: "Failed" },
          ]}
        />,
      );
      // pages: row 1 stands alone; rows 3 and 4 join. failed: rows 1-3 join.
      const points = container.querySelectorAll("[data-slot=chart-point]");
      expect(points).toHaveLength(1);
      expect(points[0]).toHaveAttribute("fill", "var(--chart-1)");
      unmount();
    }
    const { container } = renderV1(
      <Sparkline
        title="One day"
        data={[{ day: "1 Sep", pages: 5 }]}
        xKey="day"
        width={120}
        series={[{ key: "pages", label: "Pages" }]}
      />,
    );
    expect(container.querySelectorAll("[data-slot=chart-point]")).toHaveLength(
      1,
    );
  });

  it("still names the category in the tooltip when every series is a gap there", async () => {
    const rows = [
      { day: "9 Aug", pages: 10, failed: 1 },
      { day: "10 Aug", pages: null, failed: null },
      { day: "11 Aug", pages: 20, failed: 2 },
    ];
    const { container, user } = renderV1(
      <BarChart
        title="T"
        data={rows}
        xKey="day"
        width={WIDTH}
        height={HEIGHT}
        series={SERIES}
      />,
    );
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(
      container.querySelector("[data-slot=chart-tooltip]"),
    ).toHaveTextContent("10 AugPages processed–Failed pages–");
    // Recharts hides the wrapper of an empty payload; gap entries keep it shown.
    expect(container.querySelector(".recharts-tooltip-wrapper")).toHaveStyle({
      visibility: "visible",
    });
  });

  it("formats the left axis with axisFormat and the right with rightAxisFormat", () => {
    const { container } = renderV1(
      <LineChart
        {...props({
          series: [
            { key: "pages", label: "Pages" },
            { key: "failed", label: "Cost", axis: "right" },
          ],
          axisFormat: (v) => `${v}p`,
          rightAxisFormat: (v) => `$${v}`,
        })}
      />,
    );
    const ticks = (axis: Element | undefined) =>
      [...(axis?.querySelectorAll("text") ?? [])].map(
        (t) => t.textContent ?? "",
      );
    const [left, right] = [
      ...container.querySelectorAll(".recharts-yAxis-tick-labels"),
    ];
    expect(ticks(left).length).toBeGreaterThan(0);
    expect(ticks(left).every((t) => t.endsWith("p"))).toBe(true);
    expect(ticks(right).length).toBeGreaterThan(0);
    expect(ticks(right).every((t) => t.startsWith("$"))).toBe(true);
  });

  it("redraws markers and the summary when markers change, even with the same data and inline series", () => {
    const view = (markers: CartesianChartProps<Row>["markers"]) => (
      <LineChart
        {...props({
          series: [
            { key: "pages", label: "Pages processed" },
            { key: "failed", label: "Failed pages" },
          ],
          markers,
        })}
      />
    );
    const { container, rerender } = renderV1(
      view([{ index: 1, series: "pages", label: "first" }]),
    );
    const marker = () =>
      container.querySelector("[data-slot=chart-marker]")?.textContent;
    expect(marker()).toBe("first");
    rerender(view([{ index: 1, series: "pages", label: "renamed" }]));
    expect(marker()).toBe("renamed");
    expect(screen.getByText(/Marked: renamed\./)).toBeInTheDocument();
    const cx = () =>
      container
        .querySelector("[data-slot=chart-marker] circle")
        ?.getAttribute("cx");
    const before = cx();
    rerender(view([{ index: 2, series: "pages", label: "renamed" }]));
    expect(cx()).not.toBe(before);
    rerender(view([{ index: 2, series: "failed", label: "renamed" }]));
    expect(
      container.querySelector("[data-slot=chart-marker] circle"),
    ).toHaveAttribute("fill", "var(--chart-2)");
  });

  it("warns once per dropped marker while showing data, and not while loading", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const view = (state: "loading" | "ready", rows: Row[]) => (
      <LineChart
        {...props({
          state,
          data: rows,
          markers: [
            { index: 1, series: "pages", label: "peak" },
            { index: 1, series: "pages", label: "again" },
          ],
        })}
      />
    );
    const { rerender } = renderV1(view("loading", []));
    rerender(view("loading", []));
    expect(warn).not.toHaveBeenCalled();
    rerender(view("ready", [...data]));
    rerender(view("ready", [...data]));
    expect(warn.mock.calls.map(([message]) => message)).toEqual([
      'Chart marker "again" not drawn: an earlier marker already labels that point.',
    ]);
  });

  // The default locale is the runtime's, which cannot be varied in-process
  // (Intl reads it at start-up), so this pins the default formats, grouped and
  // compact, not which locale they use.
  it("formats grouped values and compact ticks by default", () => {
    const viewer = numberFormats();
    const { container } = renderV1(
      <LineChart
        {...props({ valueFormat: undefined, axisFormat: undefined })}
      />,
    );
    expect(
      screen.getByRole("cell", { name: viewer.value(2981) }),
    ).toBeInTheDocument();
    const ticks = [
      ...container.querySelectorAll(".recharts-yAxis-tick-labels text"),
    ].map((t) => t.textContent);
    expect(ticks).toContain(viewer.axis(3000));
  });

  it("warns about a reserved series key in any state, and draws no markers then", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    type Pivot = Record<string, string | number>;
    const rows: Pivot[] = [{ day: "1", a: 1, __marker_b: 2 }];
    const view = (state: "loading" | "ready") => (
      <LineChart
        title="T"
        data={rows}
        xKey="day"
        width={WIDTH}
        height={HEIGHT}
        state={state}
        series={[
          { key: "a", label: "A" },
          { key: "__marker_b", label: "B" },
        ]}
        markers={[{ index: 0, series: "a", label: "peak" }]}
      />
    );
    const { container, rerender } = renderV1(view("loading"));
    expect(warn).toHaveBeenCalledWith(
      'Chart series key "__marker_b" starts with "__marker", which the chart uses for markers; rename the field.',
    );
    rerender(view("ready"));
    expect(container.querySelector("[data-slot=chart-marker]")).toBeNull();
    expect(warn).toHaveBeenLastCalledWith(
      'Chart marker "peak" not drawn: a series key starts with "__marker", which markers reserve.',
    );
  });

  it("labels each of two series marked on the same row with its own marker", () => {
    const both = [
      { index: 1, series: "pages", label: "pages peak" },
      { index: 1, series: "failed", label: "failed peak" },
    ] as const;
    for (const Chart of [LineChart, BarChart]) {
      const { container, unmount } = renderV1(
        <Chart {...props({ markers: both })} />,
      );
      const marks = [
        ...container.querySelectorAll("[data-slot=chart-marker]"),
      ].map((m) => [
        m.textContent,
        m.querySelector("circle")?.getAttribute("fill"),
      ]);
      expect(marks).toEqual(
        expect.arrayContaining([
          ["pages peak", "var(--chart-1)"],
          ["failed peak", "var(--chart-2)"],
        ]),
      );
      expect(marks).toHaveLength(2);
      unmount();
    }
  });

  it("reads edge marker labels inward on a real line and area chart", () => {
    for (const Chart of [LineChart, AreaChart]) {
      const { container, unmount } = renderV1(
        <Chart
          {...props({
            markers: [
              { index: 0, series: "pages", label: "first" },
              { index: 1, series: "failed", label: "m" },
              { index: 2, series: "pages", label: "last" },
            ],
          })}
        />,
      );
      const anchors = Object.fromEntries(
        [...container.querySelectorAll("[data-slot=chart-marker]")].map((m) => [
          m.textContent,
          m.querySelector("text")?.getAttribute("text-anchor"),
        ]),
      );
      expect(anchors).toEqual({ first: "start", m: "middle", last: "end" });
      unmount();
    }
  });

  it("reads long bar marker labels inward at the first and last bar of a real bar chart", () => {
    const long = "10 Aug · 2,981 pages";
    const { container } = renderV1(
      <BarChart
        {...props({
          markers: [
            { index: 0, series: "pages", label: long },
            { index: 1, series: "failed", label: "m" },
            // The right-hand bar of the last group, nearest the edge.
            { index: 2, series: "failed", label: `${long} ` },
          ],
        })}
      />,
    );
    const anchors = [
      ...container.querySelectorAll("[data-slot=chart-marker]"),
    ].map((m) => [
      m.textContent,
      m.querySelector("text")?.getAttribute("text-anchor"),
    ]);
    expect(anchors).toEqual(
      expect.arrayContaining([
        [long, "start"],
        ["m", "middle"],
        [`${long} `, "end"],
      ]),
    );
  });

  it("measures bar marker labels against the plot area, which a right axis narrows", () => {
    // The last "pages" bar centres at about 315 without a right axis (plot
    // ends at 392) and about 283 with one (plot ends at 352). A 140-wide
    // label fits centred in the first case and not in the second.
    const anchorWith = (axis: "left" | "right") => {
      const { container, unmount } = renderV1(
        <BarChart
          {...props({
            series: [
              { key: "pages", label: "Pages processed" },
              { key: "failed", label: "Failed pages", axis },
            ],
            markers: [{ index: 2, series: "pages", label: "x".repeat(20) }],
          })}
        />,
      );
      const anchor = container
        .querySelector("[data-slot=chart-marker] text")
        ?.getAttribute("text-anchor");
      unmount();
      return anchor;
    };
    expect(anchorWith("left")).toBe("middle");
    expect(anchorWith("right")).toBe("end");
  });

  it("separates stacked segments with a card-coloured stroke", () => {
    const { container } = renderV1(<StackedBarChart {...props()} />);
    const segments = container.querySelectorAll(".recharts-bar-rectangle path");
    expect(segments.length).toBe(6);
    for (const s of segments) {
      expect(s).toHaveAttribute("stroke", "var(--card)");
    }
  });

  it("fills its container through ResizeObserver when no width is given", () => {
    const size = installResizeObserver();
    const { container } = renderV1(
      <BarChart {...props({ width: undefined })} />,
    );
    expect(container.querySelector("[data-slot=bar-chart]")).toHaveClass(
      "ui:w-full",
    );
    const [observed] = size.observed();
    size.resize(observed, { width: 640, height: HEIGHT });
    expect(plot(container)).toHaveAttribute("width", "640");
  });

  it.each(
    THEME_MODES,
  )("renders inside the %s theme root, so the ramp tokens resolve for that mode", (theme) => {
    const { container } = renderV1(<AreaChart {...props()} />, { theme });
    expect(plot(container).closest(".v1")).toHaveAttribute("data-theme", theme);
  });
});

describe("Sparkline", () => {
  const sparkProps = {
    title: "Pages processed, last 30 days",
    data,
    xKey: "day",
    series: [{ key: "pages", label: "Pages" }],
    width: 120,
    valueFormat: EN.value,
  } as const;

  it("draws one line with no axes, grid, legend or tooltip, as a static image", async () => {
    const { container } = renderV1(<Sparkline {...sparkProps} />);
    const svg = plot(container);
    expect(svg).toHaveAttribute("role", "img");
    expect(svg).not.toHaveAttribute("tabindex");
    expect(svg).toHaveAttribute("height", "40");
    expect(
      container.querySelector(".recharts-xAxis, .recharts-cartesian-grid"),
    ).toBeNull();
    expect(container.querySelector("[data-slot=chart-legend]")).toBeNull();
    expect(container.querySelector(`[name="Pages"]`)).toHaveAttribute(
      "stroke",
      "var(--chart-1)",
    );
    expect(
      screen.getByRole("table", { name: sparkProps.title }),
    ).toBeInTheDocument();
    expect(
      document.getElementById(svg.getAttribute("aria-describedby") ?? ""),
    ).toHaveTextContent(/^Pages processed, last 30 days\. Sparkline, 3 points/);
    await expect(container).toHaveNoA11yViolations();
  });

  it("shows a tooltip with the category on the arrow keys when asked", async () => {
    const { container, user } = renderV1(<Sparkline {...sparkProps} tooltip />);
    expect(plot(container)).toHaveAttribute("role", "application");
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(
      container.querySelector("[data-slot=chart-tooltip]"),
    ).toHaveTextContent("10 AugPages2,981");
  });

  it("still names the category in its tooltip on a gap", async () => {
    const { container, user } = renderV1(
      <Sparkline
        {...sparkProps}
        data={[
          { day: "9 Aug", pages: 10, failed: 0 },
          { day: "10 Aug", pages: null, failed: 0 },
          { day: "11 Aug", pages: 20, failed: 0 },
        ]}
        tooltip
      />,
    );
    await user.tab();
    await user.keyboard("{ArrowRight}");
    expect(
      container.querySelector("[data-slot=chart-tooltip]"),
    ).toHaveTextContent("10 AugPages–");
    expect(container.querySelector(".recharts-tooltip-wrapper")).toHaveStyle({
      visibility: "visible",
    });
  });

  it("has loading and empty states", () => {
    const { rerender } = renderV1(
      <Sparkline {...sparkProps} state="loading" />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading Pages processed, last 30 days",
    );
    rerender(
      <Sparkline
        {...sparkProps}
        data={[] as Row[]}
        emptyMessage="No pages yet"
      />,
    );
    expect(screen.getByText("No pages yet")).toBeInTheDocument();
  });
});
