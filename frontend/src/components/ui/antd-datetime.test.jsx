import { fireEvent, render } from "@testing-library/react";
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
});
