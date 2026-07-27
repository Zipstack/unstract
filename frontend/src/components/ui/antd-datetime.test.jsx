import { fireEvent, render, screen } from "@testing-library/react";
import dayjs from "dayjs";
import moment from "moment";
import { describe, expect, it, vi } from "vitest";

import {
  DatePicker,
  RangePicker,
  TimePicker,
} from "@/components/ui/antd-datetime";

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
    const { container } = render(
      <RangePicker value={[dayjs("2026-03-01"), dayjs("2026-03-31")]} />,
    );
    const inputs = container.querySelectorAll("input");
    expect(inputs[0].value).toBe("2026-03-01");
    expect(inputs[1].value).toBe("2026-03-31");
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

  it("RangePicker renders two inputs and keeps the [start, end] tuple", () => {
    const { container } = render(
      <RangePicker value={[moment("2026-03-01"), moment("2026-03-31")]} />,
    );
    const inputs = container.querySelectorAll("input");
    expect(inputs).toHaveLength(2);
    expect(inputs[0].value).toBe("2026-03-01");
    expect(inputs[1].value).toBe("2026-03-31");
  });

  it("RangePicker emits a tuple of moments", () => {
    const onChange = vi.fn();
    const { container } = render(
      <RangePicker value={[null, null]} onChange={onChange} />,
    );
    fireEvent.change(container.querySelectorAll("input")[0], {
      target: { value: "2026-03-01" },
    });

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
    it("renders preset buttons and applies the range when one is clicked", () => {
      const onChange = vi.fn();
      const preset = [moment("2026-03-01"), moment("2026-03-08")];
      render(
        <RangePicker
          value={[null, null]}
          onChange={onChange}
          presets={[{ label: "Last 7 Days", value: preset }]}
        />,
      );

      const button = screen.getByRole("button", { name: "Last 7 Days" });
      fireEvent.click(button);

      const [pair] = onChange.mock.calls[0];
      expect(pair[0].toISOString()).toBe(preset[0].toISOString());
      expect(pair[1].toISOString()).toBe(preset[1].toISOString());
    });

    it("renders no preset row when presets are not supplied", () => {
      render(<RangePicker value={[null, null]} />);
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    // MetricsDashboard blocks future dates. A native input enforces that via
    // `max`, so the predicate has to be translated into a bound.
    it("turns a no-future-dates disabledDate into a max bound", () => {
      const { container } = render(
        <RangePicker
          value={[null, null]}
          disabledDate={(current) => current && current > moment()}
        />,
      );
      const [from, to] = container.querySelectorAll("input");
      expect(from.getAttribute("max")).toBe(moment().format("YYYY-MM-DD"));
      expect(to.getAttribute("max")).toBe(moment().format("YYYY-MM-DD"));
    });

    it("leaves the inputs unbounded when no disabledDate is given", () => {
      const { container } = render(<RangePicker value={[null, null]} />);
      const input = container.querySelector("input");
      expect(input.getAttribute("max")).toBeNull();
      expect(input.getAttribute("min")).toBeNull();
    });

    // antd reports a fully-cleared range as null. MetricsDashboard's handler
    // ignores anything that is not a complete pair, so emitting null with
    // allowClear={false} would strand the dashboard on a stale range.
    it("suppresses the cleared-range emit when allowClear is false", () => {
      const onChange = vi.fn();
      const { container } = render(
        <RangePicker
          allowClear={false}
          value={[moment("2026-03-01"), null]}
          onChange={onChange}
        />,
      );
      fireEvent.change(container.querySelectorAll("input")[0], {
        target: { value: "" },
      });
      expect(onChange).not.toHaveBeenCalled();
    });

    it("still emits null for a cleared range when allowClear is default", () => {
      const onChange = vi.fn();
      const { container } = render(
        <RangePicker
          value={[moment("2026-03-01"), null]}
          onChange={onChange}
        />,
      );
      fireEvent.change(container.querySelectorAll("input")[0], {
        target: { value: "" },
      });
      expect(onChange).toHaveBeenCalledWith(null, ["", ""]);
    });

    it("fires onOk once the range becomes complete", () => {
      const onOk = vi.fn();
      const { container } = render(
        <RangePicker value={[moment("2026-03-01"), null]} onOk={onOk} />,
      );
      fireEvent.change(container.querySelectorAll("input")[1], {
        target: { value: "2026-03-31" },
      });
      expect(onOk).toHaveBeenCalledTimes(1);
    });

    it("does not fire onOk while the range is still half-filled", () => {
      const onOk = vi.fn();
      const { container } = render(
        <RangePicker value={[null, null]} onOk={onOk} />,
      );
      fireEvent.change(container.querySelectorAll("input")[0], {
        target: { value: "2026-03-01" },
      });
      expect(onOk).not.toHaveBeenCalled();
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
    it("echoes back the caller's date library rather than forcing moment", () => {
      const onChange = vi.fn();
      const { container } = render(
        <RangePicker value={[dayjs("2026-03-01"), null]} onChange={onChange} />,
      );
      fireEvent.change(container.querySelectorAll("input")[1], {
        target: { value: "2026-03-31" },
      });

      const [pair] = onChange.mock.calls[0];
      expect(dayjs.isDayjs(pair[1])).toBe(true);
      expect(moment.isMoment(pair[1])).toBe(false);
      // And it must be the date asked for, not today.
      expect(pair[1].format("YYYY-MM-DD")).toBe("2026-03-31");
    });

    it("preserves moment for callers that hold moment", () => {
      const onChange = vi.fn();
      const { container } = render(
        <RangePicker
          value={[moment("2026-03-01"), null]}
          onChange={onChange}
        />,
      );
      fireEvent.change(container.querySelectorAll("input")[1], {
        target: { value: "2026-03-31" },
      });

      const [pair] = onChange.mock.calls[0];
      expect(moment.isMoment(pair[1])).toBe(true);
      expect(pair[1].format("YYYY-MM-DD")).toBe("2026-03-31");
    });

    // The exact predicate MetricsDashboard passes, with the real dayjs.
    it("bounds a dayjs-based disabledDate to today", () => {
      const { container } = render(
        <RangePicker
          value={[dayjs().subtract(7, "day"), dayjs()]}
          disabledDate={(current) => current && current > dayjs()}
        />,
      );
      expect(container.querySelector("input").getAttribute("max")).toBe(
        moment().format("YYYY-MM-DD"),
      );
    });
  });
});
