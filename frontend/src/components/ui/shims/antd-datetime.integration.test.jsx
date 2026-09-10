import { fireEvent, render, screen } from "@testing-library/react";
import dayjs from "dayjs";
import { describe, expect, it, vi } from "vitest";
import { RangePicker } from "@/components/ui/shims/antd-datetime";

// End-to-end through the EXACT props MetricsDashboard passes.
describe("MetricsDashboard integration shape", () => {
  it("opens, shows presets + two months, and drives a 7-day range", async () => {
    const onChange = vi.fn();
    const now = dayjs("2026-07-28T10:00:00");
    render(
      <RangePicker
        value={[now.subtract(30, "day"), now]}
        onChange={onChange}
        disabledDate={(current) => current && current > now}
        allowClear={false}
        size="middle"
        presets={[
          { label: "Last 7 Days", value: [now.subtract(7, "day"), now] },
          { label: "Last 30 Days", value: [now.subtract(30, "day"), now] },
          { label: "Last 90 Days", value: [now.subtract(90, "day"), now] },
        ]}
      />,
    );

    // Trigger shows the current range.
    const trigger = screen.getByRole("button", {
      name: /2026-06-28.*2026-07-28/,
    });
    fireEvent.click(trigger);

    // Two months render.
    expect((await screen.findAllByRole("grid")).length).toBe(2);
    // Preset sidebar renders.
    for (const l of ["Last 7 Days", "Last 30 Days", "Last 90 Days"]) {
      expect(screen.getByRole("button", { name: l })).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: "Last 7 Days" }));
    const [pair] = onChange.mock.calls.at(-1);
    expect(dayjs.isDayjs(pair[0])).toBe(true);
    expect(pair[1].diff(pair[0], "day")).toBe(7);
  });
});

/**
 * jsdom has no layout engine, so it cannot catch "the popover ran off the
 * bottom of the screen". What it CAN pin is the cause: `sm:` variants track
 * the VIEWPORT, but this content lives inside a popover whose own width is
 * what matters. On a wide screen the months still stacked, leaving a 250px
 * by ~700px column that overflowed the window.
 *
 * Asserting the class contract is the cheapest guard available here; the
 * geometry itself was checked in a real browser.
 */
describe("popover layout must not depend on viewport breakpoints", () => {
  it("lays the months out in a row unconditionally", async () => {
    render(
      <RangePicker
        value={[dayjs("2026-03-01"), dayjs("2026-03-31")]}
        presets={[{ label: "Last 7 Days", value: [dayjs(), dayjs()] }]}
      />,
    );
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    expect(document.querySelector(".flex.flex-row.gap-4")).toBeTruthy();
    // A viewport-conditional row is the bug, not the fix.
    expect(document.body.innerHTML).not.toContain("sm:flex-row");
    expect(document.body.innerHTML).not.toContain("sm:flex-col");
  });

  /*
   * react-day-picker renders ONE nav for the whole calendar. Anchoring the
   * absolute prev/next buttons to `.month` pinned both to the FIRST month, so
   * with `numberOfMonths={2}` the "next" arrow sat mid-popover instead of at
   * the right edge. The positioning context has to be the months ROW.
   */
  it("anchors the nav arrows to the months row, not one month", async () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    const monthsRow = document.querySelector(".flex.flex-row.gap-4");
    expect(monthsRow.className).toContain("relative");
    // Each month must NOT create its own positioning context.
    for (const m of monthsRow.children) {
      expect(m.className).not.toContain("relative");
    }
  });

  /*
   * With `showTime` the label carries full timestamps
   * ("2026-07-02T00:00  →  2026-08-01T23:59"). A nowrap span with no min-width
   * floor forced the trigger past its container, and the Logs filter row broke
   * apart as soon as a range was picked.
   */
  it("truncates a showTime label instead of forcing the row wider", () => {
    render(
      <RangePicker
        showTime={{ format: "YYYY-MM-DDTHH:mm:ssZ[Z]" }}
        value={[dayjs("2026-07-02T00:00"), dayjs("2026-08-01T23:59")]}
      />,
    );
    const trigger = screen.getAllByRole("button")[0];
    expect(trigger.className).toContain("max-w-full");

    const label = trigger.querySelector("span:not(.shrink-0)");
    expect(label.className).toContain("truncate");
    expect(label.className).toContain("min-w-0");
    expect(label.className).not.toContain("whitespace-nowrap");
  });

  /*
   * antd's header offers a year jump (`super-prev`/`super-next` plus clickable
   * month and year buttons). The arrows here stepped by month only, so a date
   * a year away took twelve clicks.
   */
  it("offers month AND year selection, like antd's header", async () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    const selects = document.querySelectorAll("select");
    expect(selects.length).toBeGreaterThanOrEqual(2);
    const names = [...selects].map((s) => s.getAttribute("aria-label") || "");
    expect(names.some((n) => /month/i.test(n))).toBe(true);
    expect(names.some((n) => /year/i.test(n))).toBe(true);
  });

  /*
   * react-day-picker renders a dropdown caption as a <select> PLUS a visible
   * label span carrying the same text; the select is meant to lie invisibly
   * over the span and take the clicks. Styling the select as the visible
   * control drew both, so the header read "August August › 2026 2026 ›" and
   * the doubled width slid under the nav arrows.
   */
  it("draws each dropdown caption once, not twice", async () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    const monthSelect = document.querySelector("select");
    // Invisible, but still stacked over the label so it keeps the clicks.
    expect(monthSelect.className).toContain("opacity-0");
    expect(monthSelect.className).toContain("absolute");

    // The caption text appears once per month, in the label the select covers.
    const root = monthSelect.parentElement;
    const label = root.querySelector("span[aria-hidden]");
    expect(label.textContent).toBe("March");
    expect(root.className).toContain("border");
  });

  it("points a dropdown's chevron down and a nav arrow sideways", async () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    const dir = (el) =>
      el.getAttribute("class").match(/lucide-chevron-(\w+)/)?.[1] ?? "";
    const chevrons = [...document.querySelectorAll("svg.rdp-chevron")];
    // Four captions (month + year, twice) all point down; the two nav arrows
    // point left and right. Falling through to a default gave every caption a
    // rightward chevron, so none of them read as a dropdown.
    const dirs = chevrons.map(dir);
    expect(dirs.filter((d) => d === "down")).toHaveLength(4);
    expect(dirs).toContain("left");
    expect(dirs).toContain("right");
  });

  it("keeps the caption clear of the nav arrows", async () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    fireEvent.click(screen.getAllByRole("button")[0]);
    await screen.findAllByRole("grid");

    // The arrows are absolutely positioned at the calendar's outer edges, so
    // the caption reserves room for them rather than centring into them.
    const caption = document.querySelector("select").closest(".justify-center");
    expect(caption.className).toContain("px-8");
  });
});
