import PropTypes from "prop-types";

import { Tooltip } from "@/components/ui/shims/antd-overlays";
import { Typography } from "@/components/ui/shims/antd-typography";

import "./StageTimings.css";

// Canonical display order, mirroring unstract.core.stage_timings.STAGE_ORDER.
// Keys the backend adds later are rendered after these rather than dropped.
const STAGE_LABELS = {
  queue_wait: "Queue wait",
  setup: "Setup",
  source_fetch: "Source fetch",
  tool_execution: "Tool execution",
  destination: "Destination",
  finalization: "Finalization",
};

const TOOL_STAGE_LABELS = {
  extraction: "Text extraction",
  indexing: "Indexing",
  prompts: "Prompts",
};

const STAGE_HINTS = {
  queue_wait: "Time between the file being queued and a worker picking it up",
  unaccounted:
    "Time inside the run that no stage claimed — overhead between stages",
};

const TOOL_STAGE_HINTS = {};

// Fixed hues so the same stage keeps the same colour between the per-file
// breakdown and the execution-level one.
const STAGE_COLORS = {
  queue_wait: "var(--stage-queue-wait)",
  setup: "var(--stage-setup)",
  source_fetch: "var(--stage-source-fetch)",
  tool_execution: "var(--stage-tool-execution)",
  destination: "var(--stage-destination)",
  finalization: "var(--stage-finalization)",
  unaccounted: "var(--stage-unaccounted)",
};

const humanizeKey = (key) =>
  key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

const formatSeconds = (seconds) => {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  }
  if (seconds < 60) {
    return `${seconds.toFixed(seconds < 10 ? 2 : 1)}s`;
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds - mins * 60);
  return `${mins}m ${secs}s`;
};

/**
 * Order a stage map for display: known keys first in canonical order, then any
 * unrecognised key, so an older UI stays correct against a newer payload.
 */
const orderedEntries = (map, labels) => {
  if (!map || typeof map !== "object") {
    return [];
  }
  const known = Object.keys(labels).filter((key) => key in map);
  const extra = Object.keys(map).filter((key) => !(key in labels));
  return [...known, ...extra]
    .map((key) => ({
      key,
      label: labels[key] || humanizeKey(key),
      seconds: typeof map[key] === "number" ? map[key] : null,
    }))
    .filter((entry) => entry.seconds !== null);
};

const StageBar = ({ segments, total }) => {
  if (!total || total <= 0) {
    return null;
  }
  return (
    <div className="stage-timings-bar" role="presentation">
      {segments.map(({ key, label, seconds }) => {
        const pct = (seconds / total) * 100;
        // Below ~0.5% a segment renders as a hairline that reads as a border;
        // skip it rather than show a stripe nobody can hover.
        if (pct < 0.5) {
          return null;
        }
        return (
          <Tooltip key={key} title={`${label} — ${formatSeconds(seconds)}`}>
            <span
              className="stage-timings-bar-segment"
              style={{
                width: `${pct}%`,
                backgroundColor:
                  STAGE_COLORS[key] || "var(--stage-unaccounted)",
              }}
            />
          </Tooltip>
        );
      })}
    </div>
  );
};

StageBar.propTypes = {
  segments: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      label: PropTypes.string.isRequired,
      seconds: PropTypes.number.isRequired,
    }),
  ).isRequired,
  total: PropTypes.number,
};

const StageRows = ({ entries, total, hints = {} }) => (
  <ul className="stage-timings-rows">
    {entries.map(({ key, label, seconds }) => {
      const hint = hints[key];
      return (
        <li key={key} className="stage-timings-row">
          <span
            className="stage-timings-swatch"
            style={{
              backgroundColor: STAGE_COLORS[key] || "var(--stage-unaccounted)",
            }}
          />
          {/* The Tooltip shim slots onto its child, so it needs a single
              element — a bare string throws. */}
          {hint ? (
            <Tooltip title={hint}>
              <span className="stage-timings-label">{label}</span>
            </Tooltip>
          ) : (
            <span className="stage-timings-label">{label}</span>
          )}
          <span className="stage-timings-value">{formatSeconds(seconds)}</span>
          <span className="stage-timings-pct">
            {total > 0 ? `${((seconds / total) * 100).toFixed(1)}%` : ""}
          </span>
        </li>
      );
    })}
  </ul>
);

StageRows.propTypes = {
  entries: PropTypes.array.isRequired,
  total: PropTypes.number,
  hints: PropTypes.object,
};

/**
 * Renders a stage-by-stage time breakdown for one file execution, or for a
 * whole execution when given the aggregated payload.
 */
const StageTimings = ({ timings, title, compact }) => {
  if (!timings || typeof timings !== "object") {
    return (
      <Typography.Text type="secondary">
        No stage timing was recorded for this run.
      </Typography.Text>
    );
  }

  const stageEntries = orderedEntries(timings.stages, STAGE_LABELS);
  const toolEntries = orderedEntries(timings.tool_split, TOOL_STAGE_LABELS);

  if (!stageEntries.length && !toolEntries.length) {
    return (
      <Typography.Text type="secondary">
        No stage timing was recorded for this run.
      </Typography.Text>
    );
  }

  const unaccounted =
    typeof timings.unaccounted === "number" && timings.unaccounted > 0
      ? timings.unaccounted
      : 0;
  const segments = unaccounted
    ? [
        ...stageEntries,
        { key: "unaccounted", label: "Unaccounted", seconds: unaccounted },
      ]
    : stageEntries;
  // Prefer the reported total so the bar reflects the duration shown
  // elsewhere; fall back to the segments when it is missing.
  const segmentSum = segments.reduce((sum, entry) => sum + entry.seconds, 0);
  const total =
    typeof timings.total === "number" && timings.total > 0
      ? timings.total
      : segmentSum;
  // The execution-level payload carries a file count; a per-file one does not.
  const isAggregate = typeof timings.files === "number";

  return (
    <div className={`stage-timings${compact ? " stage-timings-compact" : ""}`}>
      {title && (
        <Typography.Text strong className="stage-timings-title">
          {title}
        </Typography.Text>
      )}
      <StageBar segments={segments} total={total} />
      <StageRows entries={segments} total={total} hints={STAGE_HINTS} />
      {/* The total covers the queue wait too, so it is larger than the
          Execution Time column — state it rather than leave the reader to
          wonder why the percentages are off that number. */}
      <div className="stage-timings-total">
        <span className="stage-timings-label">
          {isAggregate ? "Total time spent" : "Queued to complete"}
        </span>
        <span className="stage-timings-value">{formatSeconds(total)}</span>
      </div>
      {toolEntries.length > 0 && (
        <div className="stage-timings-sub">
          <Typography.Text type="secondary" className="stage-timings-sub-title">
            Tool execution split
          </Typography.Text>
          <StageRows
            entries={toolEntries}
            total={toolEntries.reduce((sum, entry) => sum + entry.seconds, 0)}
            hints={TOOL_STAGE_HINTS}
          />
        </div>
      )}
      {typeof timings.files === "number" && (
        <Typography.Text type="secondary" className="stage-timings-footnote">
          Summed across {timings.files} file
          {timings.files === 1 ? "" : "s"}; files run concurrently, so this is
          time spent per stage, not elapsed time.
        </Typography.Text>
      )}
    </div>
  );
};

StageTimings.propTypes = {
  timings: PropTypes.object,
  title: PropTypes.string,
  compact: PropTypes.bool,
};

export { StageTimings, formatSeconds };
