import { type ChangeObject, diffLines } from "diff";
import { splitLines } from "./tokens";

/*
 * Line diff for DiffView, computed with jsdiff (`diff`). The result indexes
 * into each side's lines rather than copying text, so the view can pull the
 * highlighted tokens of the same line.
 */

export type DiffRowKind = "context" | "added" | "removed";

/** One row of the unified layout. Line numbers are indexes from 0. */
export type DiffRow = Readonly<{
  kind: DiffRowKind;
  oldLine?: number;
  newLine?: number;
}>;

/** One side of a split row. */
export type DiffCell = Readonly<{ kind: DiffRowKind; line: number }>;

/**
 * One row of the split layout. Within a change, removed lines pair with
 * added lines in order; the shorter side is padded with empty cells.
 */
export type SplitRow = Readonly<{ old?: DiffCell; new?: DiffCell }>;

export type DiffStats = Readonly<{
  /** Separate runs of changed lines ("1 change" in frame V12). */
  changes: number;
  added: number;
  removed: number;
  /**
   * No line changed, but the texts are not identical: they differ only in
   * line endings (CRLF or LF) or a final newline, which the diff ignores.
   */
  endingsOnly: boolean;
}>;

export type LineDiff = Readonly<{
  oldLines: readonly string[];
  newLines: readonly string[];
  unified: readonly DiffRow[];
  split: readonly SplitRow[];
  stats: DiffStats;
}>;

// jsdiff compares whole lines including their newline, so "a" and "a\n"
// differ. Both sides are rejoined to end with one, as splitLines reads them;
// a difference only there is reported as `endingsOnly`, not as a change.
function joinLines(lines: readonly string[]): string {
  return lines.length === 0 ? "" : `${lines.join("\n")}\n`;
}

export type DiffLimits = Readonly<{
  /** Give up after this long (jsdiff's `timeout`). */
  timeoutMs?: number;
  /** Give up past this many inserted plus removed lines (jsdiff's `maxEditLength`). */
  maxEditLength?: number;
  /** Give up when the two texts have more lines than this between them. */
  maxLines?: number;
}>;

/**
 * jsdiff runs on the main thread and takes O(N·D) time, where D is the number
 * of added plus removed lines (an edited line counts as both). Past this many
 * it gives up, the same way on every machine, rather than freeze the page.
 */
export const DIFF_MAX_EDIT_LENGTH = 2000;
/**
 * DiffView renders (and highlights) every line at once, without windowing, so
 * two long texts with few changes must stop somewhere too: past this many
 * lines between them, both DiffView and diffStats give up.
 */
export const DIFF_MAX_LINES = 2000;
/** A backstop on slow machines; DIFF_MAX_EDIT_LENGTH is the limit that normally applies. */
export const DIFF_TIMEOUT_MS = 1000;

type DiffRun = Readonly<{
  oldLines: string[];
  newLines: string[];
  changes: ChangeObject<string>[];
  stats: DiffStats;
}>;

/** Splits each side once, applies the limits, diffs, and counts. */
function runDiff(
  oldText: string,
  newText: string,
  limits: DiffLimits,
): DiffRun | null {
  const oldLines = splitLines(oldText);
  const newLines = splitLines(newText);
  if (oldLines.length + newLines.length > (limits.maxLines ?? DIFF_MAX_LINES)) {
    return null;
  }
  const changes = diffLines(joinLines(oldLines), joinLines(newLines), {
    timeout: limits.timeoutMs ?? DIFF_TIMEOUT_MS,
    maxEditLength: limits.maxEditLength ?? DIFF_MAX_EDIT_LENGTH,
  });
  if (!changes) {
    return null;
  }
  // A change is a run of added or removed blocks with no common block between.
  let runs = 0;
  let added = 0;
  let removed = 0;
  let inRun = false;
  for (const change of changes) {
    if (!change.added && !change.removed) {
      inRun = false;
      continue;
    }
    if (!inRun) {
      runs++;
      inRun = true;
    }
    if (change.added) {
      added += change.count;
    } else {
      removed += change.count;
    }
  }
  return {
    oldLines,
    newLines,
    changes,
    stats: {
      changes: runs,
      added,
      removed,
      endingsOnly: runs === 0 && oldText !== newText,
    },
  };
}

/**
 * Diffs two texts line by line. Returns `null` when a limit is hit (by
 * default DIFF_MAX_LINES lines in all, DIFF_MAX_EDIT_LENGTH added plus removed
 * lines, or DIFF_TIMEOUT_MS), so the caller can say the texts are too large
 * to compare.
 */
export function computeLineDiff(
  oldText: string,
  newText: string,
  limits: DiffLimits = {},
): LineDiff | null {
  const diff = runDiff(oldText, newText, limits);
  if (!diff) {
    return null;
  }
  const unified: DiffRow[] = [];
  let oldLine = 0;
  let newLine = 0;
  for (const change of diff.changes) {
    for (let i = 0; i < change.count; i++) {
      if (change.added) {
        unified.push({ kind: "added", newLine: newLine++ });
      } else if (change.removed) {
        unified.push({ kind: "removed", oldLine: oldLine++ });
      } else {
        unified.push({
          kind: "context",
          oldLine: oldLine++,
          newLine: newLine++,
        });
      }
    }
  }

  const split: SplitRow[] = [];
  let i = 0;
  while (i < unified.length) {
    const row = unified[i];
    if (row.kind === "context") {
      split.push({
        old: { kind: "context", line: row.oldLine as number },
        new: { kind: "context", line: row.newLine as number },
      });
      i++;
      continue;
    }
    // A run of changed rows: jsdiff lists a change's removals before its additions.
    const gone: number[] = [];
    const came: number[] = [];
    while (i < unified.length && unified[i].kind !== "context") {
      const r = unified[i];
      if (r.kind === "removed") {
        gone.push(r.oldLine as number);
      } else {
        came.push(r.newLine as number);
      }
      i++;
    }
    for (let k = 0; k < Math.max(gone.length, came.length); k++) {
      split.push({
        ...(k < gone.length ? { old: { kind: "removed", line: gone[k] } } : {}),
        ...(k < came.length ? { new: { kind: "added", line: came[k] } } : {}),
      });
    }
  }

  return {
    oldLines: diff.oldLines,
    newLines: diff.newLines,
    unified,
    split,
    stats: diff.stats,
  };
}

/**
 * The "1 change +2 −1" counts for two texts, or `null` past the same limits
 * as DiffView. Counts only: no rows are built, but the diff itself still runs.
 */
export function diffStats(oldText: string, newText: string): DiffStats | null {
  return runDiff(oldText, newText, {})?.stats ?? null;
}

/** "1 change", "3 changes", "Only line endings differ", or "No changes". */
export function describeChanges(stats: DiffStats): string {
  if (stats.changes === 0) {
    return stats.endingsOnly ? "Only line endings differ" : "No changes";
  }
  return `${stats.changes} ${stats.changes === 1 ? "change" : "changes"}`;
}
