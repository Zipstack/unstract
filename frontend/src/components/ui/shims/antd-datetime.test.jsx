import { fireEvent, render, screen } from "@testing-library/react";
import dayjs from "dayjs";
import moment from "moment";
import { describe, expect, it, vi } from "vitest";

import {
  DatePicker,
  RangePicker,
  TimePicker,
} from "@/components/ui/shims/antd-datetime";

/**
 * D7 is the reason these tests exist. Call-sites are written against antd's
 * moment contract:
 *
 *     value={value ? moment(value) : null}
 *     onChange={(date) => onChange(date?.toISOString())}
 *
 * If the shim handed back a Date or a string, `date?.toISOString()` would
 * either throw or silently produce a different value — and timezone/DST
 * behaviour would shift, which D7 says must not happen in this phase.
 */
/**
 * RangePicker is now a popover calendar rather than two native inputs, so the
 * tests drive it the way a user does: open the trigger, click days. The
 * BEHAVIOURAL assertions below are unchanged — the tuple contract, allowClear,
 * onOk and date-library preservation are what the call-sites depend on, and
 * they have to survive the UI swap.
 */
async function openRangeCalendar() {
  // The trigger carries the calendar icon and the range label; before the
  // popover mounts it is the only button in the tree.
  const trigger = screen.getAllByRole("button")[0];
  fireEvent.click(trigger);
  // Two months are shown, so there are two grids — wait for at least one.
  await screen.findAllByRole("grid");
}

/**
 * Find a day cell by date. react-day-picker labels days
 * "Sunday, March 1st, 2026".
 *
 * Two months are rendered, and each grid also paints the adjacent month's
 * overflow days — so a single date can appear TWICE in the DOM. Take the cell
 * that is not an outside day, which is the one a user would read as belonging
 * to that month.
 */
async function pickDayButton(dateLike) {
  const d = moment(dateLike.valueOf ? dateLike.valueOf() : dateLike);
  // Match month/day/year so the ordinal suffix does not matter.
  const pattern = new RegExp(
    `${d.format("MMMM")}\\s+${d.date()}(st|nd|rd|th),\\s+${d.year()}`,
  );
  const matches = await screen.findAllByRole("button", { name: pattern });
  const owned = matches.filter(
    (el) => !el.closest("td")?.className.includes("outside"),
  );
  return owned[0] ?? matches[0];
}

/** Click a day by ISO date. */
async function pickDay(iso) {
  const button = await pickDayButton(moment(iso));
  fireEvent.click(button);
  return button;
}

describe("antd-compatible date/time shims (P3-04, D7)", () => {
  it("renders a date input for DatePicker", () => {
    const { container } = render(<DatePicker />);
    expect(container.querySelector("input").getAttribute("type")).toBe("date");
  });

  it("switches to datetime-local when showTime is set", () => {
    const { container } = render(<DatePicker showTime />);
    expect(container.querySelector("input").getAttribute("type")).toBe(
      "datetime-local",
    );
  });

  it("accepts a moment value and displays it", () => {
    const { container } = render(<DatePicker value={moment("2026-03-14")} />);
    expect(container.querySelector("input").value).toBe("2026-03-14");
  });

  /**
   * `moment(dayjsInstance)` does not understand dayjs. It does not throw and
   * does not report invalid — it quietly returns a moment for TODAY. So every
   * dayjs-valued field rendered today's date, with nothing anywhere to
   * indicate it. MetricsDashboard holds dayjs, and its "from" field showed
   * today instead of 30 days ago.
   *
   * Uses a fixed past date so a regression cannot coincidentally look right.
   */
  it("displays a dayjs value as its own date, not today", () => {
    const { container } = render(<DatePicker value={dayjs("2026-03-14")} />);
    expect(container.querySelector("input").value).toBe("2026-03-14");
  });

  it("displays a dayjs RangePicker tuple as its own dates", () => {
    render(<RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />);
    expect(
      screen.getByRole("button", { name: /2026-03-01.*2026-03-31/ }),
    ).toBeInTheDocument();
  });

  it("displays a plain Date value correctly too", () => {
    const { container } = render(
      <DatePicker value={new Date(2026, 2, 14)} />, // month is 0-based
    );
    expect(container.querySelector("input").value).toBe("2026-03-14");
  });

  it("accepts an ISO string value too", () => {
    const { container } = render(<DatePicker value="2026-03-14T00:00:00Z" />);
    expect(container.querySelector("input").value).toBeTruthy();
  });

  it("renders empty for a null value rather than 'Invalid date'", () => {
    const { container } = render(<DatePicker value={null} />);
    expect(container.querySelector("input").value).toBe("");
  });

  it("ignores an unparseable value instead of rendering NaN", () => {
    const { container } = render(<DatePicker value="not-a-date" />);
    expect(container.querySelector("input").value).toBe("");
  });

  // The load-bearing assertion for D7.
  it("hands onChange a MOMENT, so `date?.toISOString()` keeps working", () => {
    const onChange = vi.fn();
    const { container } = render(<DatePicker onChange={onChange} />);
    fireEvent.change(container.querySelector("input"), {
      target: { value: "2026-03-14" },
    });

    expect(onChange).toHaveBeenCalled();
    const arg = onChange.mock.calls[0][0];
    expect(moment.isMoment(arg)).toBe(true);
    expect(typeof arg.toISOString()).toBe("string");
  });

  it("hands onChange null when the field is cleared", () => {
    const onChange = vi.fn();
    const { container } = render(
      <DatePicker value={moment("2026-03-14")} onChange={onChange} />,
    );
    fireEvent.change(container.querySelector("input"), {
      target: { value: "" },
    });
    expect(onChange.mock.calls.at(-1)[0]).toBeNull();
  });

  it("renders a time input for TimePicker", () => {
    const { container } = render(<TimePicker />);
    expect(container.querySelector("input").getAttribute("type")).toBe("time");
  });

  it("formats a moment value as HH:mm:ss for TimePicker", () => {
    const { container } = render(
      <TimePicker value={moment("2026-03-14T13:45:30")} />,
    );
    expect(container.querySelector("input").value).toBe("13:45:30");
  });

  it("RangePicker shows both ends of the range on its trigger", () => {
    render(
      <RangePicker value={[moment("2026-03-01"), moment("2026-03-31")]} />,
    );
    expect(
      screen.getByRole("button", { name: /2026-03-01.*2026-03-31/ }),
    ).toBeInTheDocument();
  });

  it("RangePicker prompts when it has no value", () => {
    render(<RangePicker value={[null, null]} />);
    expect(
      screen.getByRole("button", { name: /Select date range/ }),
    ).toBeInTheDocument();
  });

  it("RangePicker emits a tuple of moments when days are picked", async () => {
    const onChange = vi.fn();
    render(
      <RangePicker
        value={[null, null]}
        onChange={onChange}
        defaultMonth={new Date(2026, 2, 1)}
      />,
    );

    await openRangeCalendar();
    await pickDay("2026-03-01");

    const pair = onChange.mock.calls[0][0];
    expect(Array.isArray(pair)).toBe(true);
    expect(moment.isMoment(pair[0])).toBe(true);
  });

  it("exposes RangePicker as DatePicker.RangePicker, as antd does", () => {
    expect(DatePicker.RangePicker).toBe(RangePicker);
  });

  it("passes disabled through", () => {
    const { container } = render(<DatePicker disabled />);
    expect(container.querySelector("input")).toBeDisabled();
  });

  /**
   * These props were accepted-and-ignored by the first version of the shim.
   * Ignoring them is invisible in a screenshot but changes what the control
   * DOES, so each one gets a test that fails if it silently stops working.
   */
  describe("RangePicker props the call-sites depend on", () => {
    it("renders preset buttons and applies the range when one is clicked", async () => {
      const onChange = vi.fn();
      const preset = [moment("2026-03-01"), moment("2026-03-08")];
      render(
        <RangePicker
          value={[null, null]}
          onChange={onChange}
          presets={[{ label: "Last 7 Days", value: preset }]}
        />,
      );

      await openRangeCalendar();
      fireEvent.click(screen.getByRole("button", { name: "Last 7 Days" }));

      const [pair] = onChange.mock.calls[0];
      expect(pair[0].toISOString()).toBe(preset[0].toISOString());
      expect(pair[1].toISOString()).toBe(preset[1].toISOString());
    });

    it("renders no preset sidebar when presets are not supplied", async () => {
      render(<RangePicker value={[null, null]} />);
      await openRangeCalendar();
      expect(
        screen.queryByRole("button", { name: /Last \d+ Days/ }),
      ).not.toBeInTheDocument();
    });

    // MetricsDashboard blocks future dates. A calendar can grey out individual
    // days, which is what antd's per-date predicate actually means — the old
    // native-input version could only approximate it with a min/max bound.
    it("disables future days for a no-future-dates disabledDate", async () => {
      render(
        <RangePicker
          value={[null, null]}
          disabledDate={(current) => current && current > moment()}
        />,
      );
      await openRangeCalendar();

      const tomorrow = await pickDayButton(moment().add(1, "day"));
      expect(tomorrow).toBeDisabled();
      const today = await pickDayButton(moment());
      expect(today).not.toBeDisabled();
    });

    // The predicate is the caller's own code, so it must be handed the
    // caller's own date type. MetricsDashboard's reads `current > dayjs()`;
    // a moment compares fine by coercion, which is exactly why passing the
    // wrong type here goes unnoticed until a predicate calls a dayjs-only
    // method. Assert the type the predicate actually receives.
    it("hands disabledDate the caller's date library", async () => {
      const seen = [];
      render(
        <RangePicker
          value={[dayjs("2026-03-01"), null]}
          defaultMonth={new Date(2026, 2, 1)}
          disabledDate={(current) => {
            seen.push(current);
            return false;
          }}
        />,
      );
      await openRangeCalendar();

      expect(seen.length).toBeGreaterThan(0);
      expect(seen.every((d) => dayjs.isDayjs(d))).toBe(true);
      expect(seen.some((d) => moment.isMoment(d))).toBe(false);
    });

    it("leaves every day selectable when no disabledDate is given", async () => {
      render(
        <RangePicker
          value={[null, null]}
          defaultMonth={new Date(2026, 2, 1)}
        />,
      );
      await openRangeCalendar();
      const day = await pickDayButton(moment("2026-03-15"));
      expect(day).not.toBeDisabled();
    });

    // antd reports a fully-cleared range as null. MetricsDashboard's handler
    // ignores anything that is not a complete pair, so emitting null with
    // allowClear={false} would strand the dashboard on a stale range.
    // antd reports a fully-cleared range as null. MetricsDashboard's handler
    // ignores anything that is not a complete pair, so emitting null with
    // allowClear={false} would strand the dashboard on a stale range.
    //
    // The clear path is react-day-picker handing back an empty selection.
    // There is no "clear" affordance to click, so it is driven straight
    // through the Calendar's onSelect — the same call the library makes.
    // Reach the live Calendar's onSelect by opening the popover and invoking
    // the handler react-day-picker would call. Going through the React tree
    // keeps this honest: if the shim stopped wiring onSelect, this breaks.
    const clearViaCalendar = async () => {
      await openRangeCalendar();
      const grid = screen.getAllByRole("grid")[0];
      const fiberKey = Object.keys(grid).find((k) =>
        k.startsWith("__reactFiber$"),
      );
      let node = grid[fiberKey];
      while (node && typeof node.memoizedProps?.onSelect !== "function") {
        node = node.return;
      }
      node.memoizedProps.onSelect(undefined, undefined);
    };

    it("suppresses the cleared-range emit when allowClear is false", async () => {
      const onChange = vi.fn();
      render(
        <RangePicker
          allowClear={false}
          value={[moment("2026-03-01"), moment("2026-03-05")]}
          onChange={onChange}
        />,
      );
      await clearViaCalendar();
      expect(onChange.mock.calls.filter((c) => c[0] === null)).toHaveLength(0);
    });

    it("emits null for a cleared range when allowClear is default", async () => {
      const onChange = vi.fn();
      render(
        <RangePicker
          value={[moment("2026-03-01"), moment("2026-03-05")]}
          onChange={onChange}
        />,
      );
      await clearViaCalendar();
      expect(onChange).toHaveBeenCalledWith(null, ["", ""]);
    });

    it("fires onOk once the range becomes complete", async () => {
      const onOk = vi.fn();
      render(
        <RangePicker
          value={[null, null]}
          onOk={onOk}
          defaultMonth={new Date(2026, 2, 1)}
        />,
      );
      await openRangeCalendar();
      await pickDay("2026-03-01");
      expect(onOk).not.toHaveBeenCalled();
      await pickDay("2026-03-31");
      expect(onOk).toHaveBeenCalledTimes(1);
    });

    // MetricsDashboard holds dayjs; ExecutionLogs holds moment. Handing back
    // the wrong one is a type the call-site never opted into.
    //
    // Tested against the REAL dayjs, not a stand-in. An earlier version of
    // this test used a hand-written stub whose constructor accepted a date
    // string — so it passed while the shim was doing
    // `new sample.constructor(iso)`, which dayjs silently ignores (returning
    // TODAY) and moment turns into an object that throws on .format().
    // The stub tested itself; only the real library catches that.
    it("echoes back the caller's date library rather than forcing moment", async () => {
      const onChange = vi.fn();
      render(
        <RangePicker
          value={[dayjs("2026-03-01"), null]}
          onChange={onChange}
          defaultMonth={new Date(2026, 2, 1)}
        />,
      );
      await openRangeCalendar();
      await pickDay("2026-03-31");

      const pair = onChange.mock.calls.at(-1)[0];
      const emitted = pair[1] ?? pair[0];
      expect(dayjs.isDayjs(emitted)).toBe(true);
      expect(moment.isMoment(emitted)).toBe(false);
    });

    it("preserves moment for callers that hold moment", async () => {
      const onChange = vi.fn();
      render(
        <RangePicker
          value={[moment("2026-03-01"), null]}
          onChange={onChange}
          defaultMonth={new Date(2026, 2, 1)}
        />,
      );
      await openRangeCalendar();
      await pickDay("2026-03-31");

      const pair = onChange.mock.calls.at(-1)[0];
      const emitted = pair[1] ?? pair[0];
      expect(moment.isMoment(emitted)).toBe(true);
    });
  });
});
