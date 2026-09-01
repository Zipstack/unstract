import { Calendar as CalendarIcon } from "lucide-react";
import moment from "moment";
import * as React from "react";

import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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

/**
 * The antd date/time surface these shims accept.
 *
 * These deliberately exchange MOMENT objects rather than Dates or strings
 * (D7): call-sites hold moments, and converting the date type would change
 * timezone/DST behaviour, which belongs in its own reviewed change. The value
 * types below say so explicitly.
 *
 * `MomentLike` is structural on purpose — anything exposing `valueOf()` (a
 * moment, a dayjs instance, a Date) is normalised through the epoch instant.
 * That normalisation exists because `moment(dayjsInstance)` silently returns
 * TODAY and reports `isValid() === true`, so the wrong date rendered with no
 * error anywhere.
 */
interface MomentLike {
  valueOf: () => number;
  format?: (pattern?: string) => string;
  toDate?: () => Date;
  isValid?: () => boolean;
  clone?: () => MomentLike;
}

/** What the pickers accept as a value: a moment/dayjs/Date, or an ISO string. */
type DateValue = MomentLike | Date | string | null | undefined;

interface DatePickerProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "size"
  > {
  value?: DateValue;
  /** antd hands back (moment, isoString), matching what call-sites destructure. */
  onChange?: (value: MomentLike | null, dateString: string) => void;
  showTime?: boolean;
  /** Display pattern. The native control renders it, so this is accepted, not applied. */
  format?: string;
  size?: "small" | "middle" | "large";
}

interface TimePickerProps
  extends Omit<
    React.InputHTMLAttributes<HTMLInputElement>,
    "value" | "onChange" | "size"
  > {
  value?: DateValue;
  onChange?: (value: MomentLike | null, timeString: string) => void;
  format?: string;
  size?: "small" | "middle" | "large";
}

/** antd's range value is a [start, end] tuple. */
type RangeValue = [MomentLike | null, MomentLike | null] | null;

interface RangePickerProps
  extends Omit<
    React.HTMLAttributes<HTMLDivElement>,
    "value" | "onChange" | "defaultValue"
  > {
  value?: RangeValue;
  onChange?: (value: RangeValue, dateStrings: [string, string]) => void;
  /** Fired once the range is complete, as antd does. */
  onOk?: (value: RangeValue) => void;
  showTime?: boolean;
  disabled?: boolean;
  /** Quick-select shortcuts shown beside the calendar. */
  presets?: Array<{ label: React.ReactNode; value: RangeValue }>;
  disabledDate?: (current: MomentLike) => boolean;
  allowClear?: boolean;
  /** Month the calendar opens on. */
  defaultMonth?: Date;
  format?: string;
  size?: "small" | "middle" | "large";
}

/** ISO → the value shape a native input expects. */
function toInputValue(
  value: DateValue,
  type: "date" | "time" | "datetime-local",
): string {
  if (!value) {
    return "";
  }
  // `moment(dayjsInstance)` does NOT understand dayjs: it returns a moment for
  // TODAY and reports isValid() === true, so the wrong date renders with no
  // error anywhere. MetricsDashboard holds dayjs, which is why its start field
  // showed today instead of 30 days ago. Anything exposing valueOf() (dayjs,
  // moment, Date) is normalised through the epoch instant first.
  const normalised: number | string | Date =
    !moment.isMoment(value) && typeof value?.valueOf === "function"
      ? value.valueOf()
      : (value as string | Date);
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
const DatePickerBase = React.forwardRef<HTMLInputElement, DatePickerProps>(
  function DatePicker(
    {
      value,
      onChange,
      showTime,
      disabled,
      placeholder,
      format: _format,
      size: _size,
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
  },
);

/** antd `<TimePicker value onChange>`. */
const TimePicker = React.forwardRef<HTMLInputElement, TimePickerProps>(
  function TimePicker(
    {
      value,
      onChange,
      disabled,
      placeholder,
      format: _format,
      size: _size,
      className,
      ...props
    },
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
  },
);

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
function likeSample(
  sample: MomentLike | Date | string | null | undefined,
  isoish?: string | null,
): MomentLike | null {
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
  const cloneable =
    sample && typeof sample === "object" && "clone" in sample
      ? (sample as MomentLike)
      : null;
  if (typeof cloneable?.clone === "function") {
    try {
      const moved = applyInstant(cloneable.clone(), millis);
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
function applyInstant(clone: MomentLike, millis: number): MomentLike | null {
  const base = moment(millis);
  const parts: Array<[string, number]> = [
    ["year", base.year()],
    ["month", base.month()],
    ["date", base.date()],
    ["hour", base.hour()],
    ["minute", base.minute()],
    ["second", base.second()],
    ["millisecond", base.millisecond()],
  ];
  let current: MomentLike | null = clone;
  for (const [unit, value] of parts) {
    // moment and dayjs both expose year()/month()/date()/… but share no type,
    // so this read is reflection by nature. Cast here, at the probe, rather
    // than widening MomentLike — which would stop moment.Moment satisfying it.
    const setter = (current as unknown as Record<string, unknown>)[unit];
    if (typeof setter !== "function") {
      return null;
    }
    current = ((setter as (v: number) => MomentLike | undefined).call(
      current,
      value,
    ) ?? current) as MomentLike;
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
const RangePicker = React.forwardRef<HTMLDivElement, RangePickerProps>(
  function RangePicker(
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
      defaultMonth,
      format: _format,
      size: _size,
      ...props
    },
    ref,
  ) {
    const type = showTime ? "datetime-local" : "date";
    const [start, end] = value ?? [null, null];
    const sample = start ?? end ?? presets?.[0]?.value?.[0] ?? null;

    const emit = (nextStart: MomentLike | null, nextEnd: MomentLike | null) => {
      const cleared = !nextStart && !nextEnd;
      // antd reports a cleared range as null. With allowClear={false} the
      // call-site never wants that, so hold the previous pair instead.
      if (cleared && !allowClear) {
        return;
      }
      const pair: RangeValue = cleared ? null : [nextStart, nextEnd];
      onChange?.(pair, [
        toInputValue(nextStart, type),
        toInputValue(nextEnd, type),
      ]);
      if (nextStart && nextEnd) {
        onOk?.([nextStart, nextEnd]);
      }
    };

    /**
     * antd's `disabledDate(current)` answers per-date, and so does the
     * calendar's `disabled` — so the predicate maps straight across. The earlier
     * native-input version had to probe outward for a min/max bound because an
     * `<input type=date>` only understands those two attributes; a calendar can
     * grey out individual days, which is what the prop actually means.
     */
    const isDayDisabled = React.useMemo(() => {
      if (typeof disabledDate !== "function") {
        return undefined;
      }
      return (day: Date) => {
        try {
          const probe = likeSample(sample, day.toISOString());
          return probe ? Boolean(disabledDate(probe)) : false;
        } catch {
          // A predicate that cannot cope with the probe must not take the
          // calendar down with it; treat the day as selectable.
          return false;
        }
      };
    }, [disabledDate, sample]);

    type Preset = NonNullable<RangePickerProps["presets"]>[number];

    const applyPreset = (preset: Preset) => {
      const [presetStart, presetEnd] = preset.value ?? [null, null];
      onChange?.(
        [presetStart, presetEnd],
        [toInputValue(presetStart, type), toInputValue(presetEnd, type)],
      );
      if (presetStart && presetEnd) {
        onOk?.([presetStart, presetEnd]);
      }
    };

    const [open, setOpen] = React.useState(false);

    /** The calendar speaks native Date; the call-sites speak moment/dayjs. */
    const selectedRange = React.useMemo(() => {
      const from = start
        ? new Date(moment(start.valueOf()).valueOf())
        : undefined;
      const to = end ? new Date(moment(end.valueOf()).valueOf()) : undefined;
      return from || to ? { from, to } : undefined;
    }, [start, end]);

    /**
     * Tracks which end the next click fills.
     *
     * react-day-picker reports `{from, to}` with BOTH set to the clicked day on
     * every click — it does not distinguish "started a range" from "finished
     * one". Taken at face value that makes each click look like a complete
     * range, so `onOk` would fire on the first click and the second click would
     * start over instead of closing the range. antd treats the first click as
     * the start and the second as the end, so the anchor is tracked here.
     */
    const [anchor, setAnchor] = React.useState<MomentLike | null>(null);

    const handleSelect = (
      range: { from?: Date; to?: Date } | undefined,
      clickedDay?: Date,
    ) => {
      const day = clickedDay ?? range?.to ?? range?.from;
      if (!day) {
        // Deselect: react-day-picker clears the range.
        setAnchor(null);
        emit(null, null);
        return;
      }

      const picked = likeSample(sample, day.toISOString());

      if (!anchor) {
        // First click: open a new range. Report the half-filled pair the way
        // antd does, so a call-site watching onChange sees the start land.
        setAnchor(picked);
        emit(picked, null);
        return;
      }

      // Second click: close the range, ordering the ends so a backwards
      // selection still yields start <= end.
      if (!picked) {
        return;
      }
      const [from, to] =
        picked.valueOf() < anchor.valueOf()
          ? [picked, anchor]
          : [anchor, picked];
      setAnchor(null);
      emit(from, to);
      setOpen(false);
    };

    const label =
      start || end
        ? `${toInputValue(start, type) || "…"}  →  ${toInputValue(end, type) || "…"}`
        : "Select date range";

    return (
      <span
        ref={ref}
        className={cn("inline-flex items-center", className)}
        {...props}
      >
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              disabled={disabled}
              className={cn(
                "ant-picker ant-picker-range inline-flex h-9 max-w-full cursor-pointer items-center gap-2",
                "rounded-md border border-input bg-transparent px-3 py-1",
                "text-sm shadow-sm transition-colors",
                "hover:bg-accent hover:text-accent-foreground",
                "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                "disabled:cursor-not-allowed disabled:opacity-50",
                !start && !end && "text-muted-foreground",
              )}
            >
              <CalendarIcon className="size-4 shrink-0" aria-hidden="true" />
              {/*
               * `min-w-0` + `truncate`, not a bare `whitespace-nowrap`. With
               * `showTime` the label carries full timestamps
               * ("2026-07-02T00:00  →  2026-08-01T23:59"), and a nowrap span
               * with no min-width floor forces the button past its container —
               * the Logs filter row broke apart as soon as a range was picked.
               */}
              <span className="min-w-0 truncate">{label}</span>
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <div className="flex flex-row">
              {presets?.length ? (
                <div
                  className={cn(
                    // Not `sm:` variants: those track the viewport, but this
                    // sits inside a popover and stacked into a tall narrow
                    // column that overflowed the window.
                    "flex w-40 shrink-0 flex-col gap-1 border-r border-border p-2",
                  )}
                >
                  {presets.map((preset) => (
                    <button
                      // Safe as a key because every call-site in both repos
                      // labels presets with a plain string ("Last 7 Days" &c.).
                      // Two ELEMENT labels would both stringify to
                      // "[object Object]" and collide.
                      key={String(preset.label)}
                      type="button"
                      onClick={() => {
                        applyPreset(preset);
                        setOpen(false);
                      }}
                      className={cn(
                        "cursor-pointer whitespace-nowrap rounded-md px-2 py-1.5 text-left text-sm",
                        "hover:bg-accent hover:text-accent-foreground",
                        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                      )}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              ) : null}
              <Calendar
                mode="range"
                numberOfMonths={2}
                defaultMonth={defaultMonth ?? selectedRange?.from}
                selected={selectedRange}
                onSelect={handleSelect}
                disabled={isDayDisabled}
                /*
                 * antd's header offers a YEAR jump as well as a month one: a
                 * `super-prev`/`super-next` pair plus clickable month and year
                 * buttons. The arrows here step by month only, so picking a
                 * date a year out meant twelve clicks. Dropdown captions give
                 * back the direct month AND year selection.
                 */
                captionLayout="dropdown"
                startMonth={new Date(new Date().getFullYear() - 5, 0)}
                endMonth={new Date(new Date().getFullYear() + 5, 11)}
              />
            </div>
          </PopoverContent>
        </Popover>
      </span>
    );
  },
);

const DatePicker = Object.assign(DatePickerBase, { RangePicker });

export { DatePicker, RangePicker, TimePicker };
