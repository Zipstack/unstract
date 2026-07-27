import moment from "moment";
import * as React from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * antd-compatible `DatePicker` / `TimePicker` / `RangePicker` (P3-04).
 *
 * Built on native `<input type="date|datetime-local|time">` rather than
 * `react-day-picker`: every call-site here is a plain date/time field, not a
 * calendar surface, so a full calendar component would be more machinery than
 * the UI actually uses.
 *
 * ## The behavioural contract (D7)
 *
 * antd's pickers exchange **moment objects**, and call-sites depend on that:
 *
 *     value={value ? moment(value) : null}
 *     onChange={(date) => onChange(date?.toISOString())}
 *
 * `moment` is still a direct dependency, so rather than change every call-site
 * to a different date type — which is the behaviour-affecting half of D7 —
 * these components keep exchanging moment objects. That confines the swap to
 * the widget layer and leaves timezone/DST handling exactly as it was.
 *
 * Removing moment itself is deliberately NOT bundled in here: it changes
 * timezone semantics and deserves its own reviewed change (D7 says as much).
 */

/** ISO → the value shape a native input expects. */
function toInputValue(value, type) {
  if (!value) {
    return "";
  }
  const m = moment.isMoment(value) ? value : moment(value);
  if (!m.isValid()) {
    return "";
  }
  if (type === "time") {
    return m.format("HH:mm:ss");
  }
  if (type === "datetime-local") {
    return m.format("YYYY-MM-DDTHH:mm:ss");
  }
  return m.format("YYYY-MM-DD");
}

/**
 * antd `<DatePicker showTime value onChange>`.
 * `onChange` receives a moment (or null), matching antd.
 */
const DatePicker = React.forwardRef(function DatePicker(
  {
    value,
    onChange,
    showTime,
    disabled,
    placeholder,
    format,
    className,
    ...props
  },
  ref,
) {
  const type = showTime ? "datetime-local" : "date";
  return (
    <Input
      ref={ref}
      type={type}
      disabled={disabled}
      placeholder={placeholder}
      value={toInputValue(value, type)}
      className={cn("w-auto", className)}
      onChange={(e) => {
        const raw = e.target.value;
        onChange?.(raw ? moment(raw) : null, raw);
      }}
      {...props}
    />
  );
});

/** antd `<TimePicker value onChange>`. */
const TimePicker = React.forwardRef(function TimePicker(
  { value, onChange, disabled, placeholder, format, className, ...props },
  ref,
) {
  return (
    <Input
      ref={ref}
      type="time"
      step="1"
      disabled={disabled}
      placeholder={placeholder}
      value={toInputValue(value, "time")}
      className={cn("w-auto", className)}
      onChange={(e) => {
        const raw = e.target.value;
        onChange?.(raw ? moment(raw, "HH:mm:ss") : null, raw);
      }}
      {...props}
    />
  );
});

/**
 * antd `<DatePicker.RangePicker value={[start, end]} onChange>`.
 * Call-sites read `value?.[0]` / `value?.[1]`, so the tuple shape is kept.
 */
const RangePicker = React.forwardRef(function RangePicker(
  { value, onChange, showTime, disabled, className, ...props },
  ref,
) {
  const type = showTime ? "datetime-local" : "date";
  const [start, end] = value ?? [null, null];

  const emit = (nextStart, nextEnd) => {
    const pair = [nextStart, nextEnd];
    onChange?.(pair.every((d) => !d) ? null : pair, [
      toInputValue(nextStart, type),
      toInputValue(nextEnd, type),
    ]);
  };

  return (
    <span
      ref={ref}
      className={cn("inline-flex items-center gap-1", className)}
      {...props}
    >
      <Input
        type={type}
        disabled={disabled}
        value={toInputValue(start, type)}
        className="w-auto"
        onChange={(e) =>
          emit(e.target.value ? moment(e.target.value) : null, end)
        }
      />
      <span className="text-muted-foreground">→</span>
      <Input
        type={type}
        disabled={disabled}
        value={toInputValue(end, type)}
        className="w-auto"
        onChange={(e) =>
          emit(start, e.target.value ? moment(e.target.value) : null)
        }
      />
    </span>
  );
});

DatePicker.RangePicker = RangePicker;

export { DatePicker, RangePicker, TimePicker };
