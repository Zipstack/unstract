import { fireEvent, render, screen } from "@testing-library/react";
import dayjs from "dayjs";
import { describe, expect, it, vi } from "vitest";
import { RangePicker } from "@/components/ui/antd-datetime";

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
});
