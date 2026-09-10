import cronstrue from "cronstrue";
import PropTypes from "prop-types";
import { useMemo, useState } from "react";

import { Modal } from "@/components/ui/shims/antd-overlays";
import { cn } from "@/lib/utils";

/**
 * Cron schedule picker.
 *
 * Replaces `react-js-cron`, which was the LAST thing pulling antd into the
 * dependency tree — a 58MB framework serving one 38-line component. Hand-rolled
 * on the existing primitives rather than swapping in another library, because a
 * new dependency is a new transitive surface and removing exactly that is the
 * point of this change.
 *
 * The contract is unchanged: `setCronValue` receives a standard 5-field cron
 * string, and the parent (EtlTaskDeploy) keeps rendering the human-readable
 * summary itself via cronstrue.
 *
 * Known and deliberately NOT changed here: the picker opens at the default
 * schedule rather than loading the pipeline's current one. That was true of the
 * react-js-cron version too, and fixing it means changing the call-site's
 * contract, which belongs in its own change.
 */

const PERIODS = [
  { key: "hour", label: "Every hour" },
  { key: "day", label: "Every day" },
  { key: "week", label: "Every week" },
  { key: "month", label: "Every month" },
  { key: "custom", label: "Custom expression" },
];

const WEEKDAYS = [
  { value: 0, label: "Sunday" },
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
];

const range = (n) => Array.from({ length: n }, (_, i) => i);
const pad = (n) => String(n).padStart(2, "0");

/** Compose the 5-field expression: minute hour day-of-month month day-of-week */
function buildCron({ period, minute, hour, weekday, monthDay }) {
  switch (period) {
    case "hour":
      return `${minute} * * * *`;
    case "day":
      return `${minute} ${hour} * * *`;
    case "week":
      return `${minute} ${hour} * * ${weekday}`;
    case "month":
      return `${minute} ${hour} ${monthDay} * *`;
    default:
      return "";
  }
}

/**
 * cronstrue is the same parser the call-site uses for its summary, so if it
 * accepts the expression the surrounding UI will too. Cheaper and stricter
 * than hand-rolling a validator.
 */
function describe(expression) {
  if (!expression) {
    return { ok: false, text: "Enter a cron expression." };
  }
  try {
    return { ok: true, text: cronstrue.toString(expression) };
  } catch {
    return { ok: false, text: "Not a valid cron expression." };
  }
}

/** Bare <select>, styled to match the app's Input. */
function Field({ label, value, onChange, children }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "h-9 rounded-md border border-input bg-transparent px-2 py-1 text-sm",
          "shadow-sm transition-colors",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        )}
      >
        {children}
      </select>
    </label>
  );
}

Field.propTypes = {
  label: PropTypes.string.isRequired,
  value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]).isRequired,
  onChange: PropTypes.func.isRequired,
  children: PropTypes.node,
};

function CronGenerator({ open, showCronGenerator, setCronValue }) {
  const [period, setPeriod] = useState("hour");
  const [minute, setMinute] = useState(0);
  const [hour, setHour] = useState(0);
  const [weekday, setWeekday] = useState(1);
  const [monthDay, setMonthDay] = useState(1);
  const [custom, setCustom] = useState("0 * * * *");

  const expression = useMemo(() => {
    if (period === "custom") {
      return custom.trim();
    }
    return buildCron({ period, minute, hour, weekday, monthDay });
  }, [period, minute, hour, weekday, monthDay, custom]);

  const summary = useMemo(() => describe(expression), [expression]);

  const handleCancel = () => {
    showCronGenerator(false);
  };

  const updateCron = () => {
    // Guard the OK path rather than each keystroke: a half-typed custom
    // expression should not be rejected while it is still being typed.
    if (!summary.ok) {
      return;
    }
    setCronValue(expression);
    handleCancel();
  };

  const showTime = period !== "hour" && period !== "custom";

  return (
    <Modal
      title="Choose Cron schedule"
      open={open}
      maskClosable={false}
      closable={false}
      onCancel={handleCancel}
      onOk={updateCron}
      okButtonProps={{ disabled: !summary.ok }}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-3">
          <Field label="Repeat" value={period} onChange={setPeriod}>
            {PERIODS.map((p) => (
              <option key={p.key} value={p.key}>
                {p.label}
              </option>
            ))}
          </Field>

          {period === "week" && (
            <Field label="On" value={weekday} onChange={(v) => setWeekday(+v)}>
              {WEEKDAYS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </Field>
          )}

          {period === "month" && (
            <Field
              label="Day of month"
              value={monthDay}
              onChange={(v) => setMonthDay(+v)}
            >
              {range(31).map((d) => (
                <option key={d + 1} value={d + 1}>
                  {d + 1}
                </option>
              ))}
            </Field>
          )}

          {showTime && (
            <Field label="Hour" value={hour} onChange={(v) => setHour(+v)}>
              {range(24).map((h) => (
                <option key={h} value={h}>
                  {pad(h)}
                </option>
              ))}
            </Field>
          )}

          {period !== "custom" && (
            <Field
              label="Minute"
              value={minute}
              onChange={(v) => setMinute(+v)}
            >
              {range(60).map((m) => (
                <option key={m} value={m}>
                  {pad(m)}
                </option>
              ))}
            </Field>
          )}
        </div>

        {period === "custom" && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Cron expression</span>
            <input
              type="text"
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="minute hour day-of-month month day-of-week"
              className={cn(
                "h-9 rounded-md border border-input bg-transparent px-3 py-1",
                "font-mono text-sm shadow-sm transition-colors",
                "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
              )}
            />
          </label>
        )}

        <div className="rounded-md border border-border bg-muted px-3 py-2">
          <div className="font-mono text-sm">{expression || "—"}</div>
          <div
            className={cn(
              "mt-1 text-xs",
              summary.ok ? "text-muted-foreground" : "text-destructive",
            )}
          >
            {summary.text}
          </div>
        </div>
      </div>
    </Modal>
  );
}

CronGenerator.propTypes = {
  open: PropTypes.bool.isRequired,
  showCronGenerator: PropTypes.func.isRequired,
  setCronValue: PropTypes.func.isRequired,
};

export default CronGenerator;
