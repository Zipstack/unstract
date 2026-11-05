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
  Sparkline,
  StackedBarChart,
} from "./index";

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

  it("has loading and empty states", () => {
    const { rerender } = renderV1(
      <Sparkline {...sparkProps} state="loading" />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading Pages processed, last 30 days",
    );
    rerender(
      <Sparkline {...sparkProps} data={[]} emptyMessage="No pages yet" />,
    );
    expect(screen.getByText("No pages yet")).toBeInTheDocument();
  });
});
