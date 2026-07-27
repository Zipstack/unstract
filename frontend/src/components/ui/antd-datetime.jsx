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
  // `moment(dayjsInstance)` does NOT understand dayjs: it returns a moment for
  // TODAY and reports isValid() === true, so the wrong date renders with no
  // error anywhere. MetricsDashboard holds dayjs, which is why its start field
  // showed today instead of 30 days ago. Anything exposing valueOf() (dayjs,
  // moment, Date) is normalised through the epoch instant first.
  const normalised =
    !moment.isMoment(value) && typeof value?.valueOf === "function"
      ? value.valueOf()
      : value;
  const m = moment.isMoment(value) ? value : moment(normalised);
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
 * Rebuild a date in whatever library the CALLER is using.
 *
 * ExecutionLogs passes moment objects; MetricsDashboard passes dayjs. Both
 * expose the same `.clone()`/`.toISOString()` surface, so hardcoding moment
 * on the way out handed MetricsDashboard a moment where its state held dayjs.
 * Nothing crashed — the two APIs overlap where that code touches them — but
 * it is a type the call-site never opted into, and it silently reverses D7's
 * promise that the widget layer does not change what flows through it.
 *
 * `sample` is a value we already received from the caller, so cloning it
 * keeps their library, its locale and its timezone config.
 */
function likeSample(sample, isoish) {
  if (!isoish) {
    return null;
  }
  const millis = moment(isoish).valueOf();
  if (Number.isNaN(millis)) {
    return null;
  }

  // NOT `new sample.constructor(isoish)`. That looks right and is wrong for
  // both libraries actually in use: dayjs's internal constructor takes a
  // config OBJECT, so handed a string it ignores it and silently returns
  // today; moment's returns an object that throws on .format(). Either way
  // the caller gets a confidently-wrong date.
  //
  // `.clone()` then re-point the instant. Both libraries expose clone(), and
  // dayjs's immutable setters return a new instance while moment's mutate in
  // place and return this — assigning the result covers both.
  if (typeof sample?.clone === "function") {
    try {
      const moved = applyInstant(sample.clone(), millis);
      if (moved?.isValid?.() && moved.valueOf() === millis) {
        return moved;
      }
    } catch {
      // Fall through to moment below.
    }
  }
  return moment(isoish);
}

/**
 * Re-point a cloned date instance at `millis`, tolerating both the mutable
 * (moment) and immutable (dayjs) setter conventions.
 */
function applyInstant(clone, millis) {
  const base = moment(millis);
  const parts = [
    ["year", base.year()],
    ["month", base.month()],
    ["date", base.date()],
    ["hour", base.hour()],
    ["minute", base.minute()],
    ["second", base.second()],
    ["millisecond", base.millisecond()],
  ];
  let current = clone;
  for (const [unit, value] of parts) {
    if (typeof current?.[unit] !== "function") {
      return null;
    }
    current = current[unit](value) ?? current;
  }
  return current;
}

/**
 * antd `<DatePicker.RangePicker value={[start, end]} onChange>`.
 * Call-sites read `value?.[0]` / `value?.[1]`, so the tuple shape is kept.
 *
 * Native inputs rather than a calendar popup (see the module note), but the
 * props below are honoured because dropping them changes BEHAVIOUR, not just
 * appearance:
 *
 *   - `presets`      — MetricsDashboard's "Last 7/30/90 Days" buttons. These
 *                      are the primary way the range is set; without them the
 *                      control looks complete while its main affordance is
 *                      missing.
 *   - `disabledDate` — bounds the pickable range. MetricsDashboard uses it to
 *                      block future dates; ignoring it let users query
 *                      tomorrow. Mapped onto the inputs' min/max, which is
 *                      what a native input can enforce.
 *   - `allowClear`   — antd defaults to true. MetricsDashboard passes false
 *                      because its handler ignores anything that is not a
 *                      complete pair, so a cleared range would freeze the UI.
 *   - `onOk`         — antd fires this on the popup's confirm button. There is
 *                      no popup here, so it fires when a range becomes
 *                      complete, which is when the call-site expects it.
 */
const RangePicker = React.forwardRef(function RangePicker(
  {
    value,
    onChange,
    onOk,
    showTime,
    disabled,
    presets,
    disabledDate,
    allowClear = true,
    className,
    format: _format,
    size: _size,
    ...props
  },
  ref,
) {
  const type = showTime ? "datetime-local" : "date";
  const [start, end] = value ?? [null, null];
  const sample = start ?? end ?? presets?.[0]?.value?.[0] ?? null;

  const emit = (nextStart, nextEnd) => {
    const cleared = !nextStart && !nextEnd;
    // antd reports a cleared range as null. With allowClear={false} the
    // call-site never wants that, so hold the previous pair instead.
    if (cleared && !allowClear) {
      return;
    }
    const pair = cleared ? null : [nextStart, nextEnd];
    onChange?.(pair, [
      toInputValue(nextStart, type),
      toInputValue(nextEnd, type),
    ]);
    if (nextStart && nextEnd) {
      onOk?.([nextStart, nextEnd]);
    }
  };

  /**
   * antd's `disabledDate(current)` answers per-date. A native input only takes
   * min/max, so probe outward from today to find the first blocked day in each
   * direction and use that as the bound. This covers the shapes actually used
   * (a one-sided "no future dates" / "no dates before X") and degrades to
   * unbounded for anything more exotic rather than guessing wrong.
   */
  const bounds = React.useMemo(() => {
    if (typeof disabledDate !== "function") {
      return {};
    }
    const probe = (direction) => {
      const cursor = moment().startOf("day");
      let previous = null;
      // A two-year window: far enough for the dashboard ranges, bounded so a
      // predicate that disables nothing cannot spin.
      for (let i = 0; i <= 730; i++) {
        const day = cursor.clone().add(direction * i, "day");
        if (disabledDate(likeSample(sample, day.toISOString()))) {
          return previous;
        }
        previous = day;
      }
      return null;
    };
    const max = probe(1);
    const min = probe(-1);
    return {
      ...(max ? { max: toInputValue(max, type) } : {}),
      ...(min ? { min: toInputValue(min, type) } : {}),
    };
  }, [disabledDate, sample, type]);

  const applyPreset = (preset) => {
    const [presetStart, presetEnd] = preset.value ?? [null, null];
    onChange?.(
      [presetStart, presetEnd],
      [toInputValue(presetStart, type), toInputValue(presetEnd, type)],
    );
    if (presetStart && presetEnd) {
      onOk?.([presetStart, presetEnd]);
    }
  };

  return (
    <span
      ref={ref}
      className={cn("inline-flex flex-wrap items-center gap-1", className)}
      {...props}
    >
      <Input
        type={type}
        disabled={disabled}
        value={toInputValue(start, type)}
        className="w-auto"
        {...bounds}
        onChange={(e) => emit(likeSample(sample, e.target.value) ?? null, end)}
      />
      <span className="text-muted-foreground">→</span>
      <Input
        type={type}
        disabled={disabled}
        value={toInputValue(end, type)}
        className="w-auto"
        {...bounds}
        onChange={(e) =>
          emit(start, likeSample(sample, e.target.value) ?? null)
        }
      />
      {presets?.length ? (
        <span className="ml-1 inline-flex items-center gap-1">
          {presets.map((preset) => (
            <button
              key={preset.label}
              type="button"
              disabled={disabled}
              onClick={() => applyPreset(preset)}
              className={cn(
                "rounded-md border border-border px-2 py-1 text-xs font-medium",
                "hover:bg-accent hover:text-accent-foreground",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {preset.label}
            </button>
          ))}
        </span>
      ) : null}
    </span>
  );
});

DatePicker.RangePicker = RangePicker;

export { DatePicker, RangePicker, TimePicker };
