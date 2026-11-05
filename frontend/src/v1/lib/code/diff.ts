import { diffLines } from "diff";
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
}>;

export type LineDiff = Readonly<{
  oldLines: readonly string[];
  newLines: readonly string[];
  unified: readonly DiffRow[];
  split: readonly SplitRow[];
  stats: DiffStats;
}>;

// jsdiff compares whole lines including their newline, so "a" and "a\n"
// differ. Both sides are normalised to end with one, as splitLines reads them.
function normalise(text: string): string {
  const lines = splitLines(text);
  return lines.length === 0 ? "" : `${lines.join("\n")}\n`;
}

/** Diffs two texts line by line. */
export function computeLineDiff(oldText: string, newText: string): LineDiff {
  const oldSource = normalise(oldText);
  const newSource = normalise(newText);
  const unified: DiffRow[] = [];
  let oldLine = 0;
  let newLine = 0;
  for (const change of diffLines(oldSource, newSource)) {
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
  let changes = 0;
  let added = 0;
  let removed = 0;
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
    changes++;
    removed += gone.length;
    added += came.length;
    for (let k = 0; k < Math.max(gone.length, came.length); k++) {
      split.push({
        ...(k < gone.length ? { old: { kind: "removed", line: gone[k] } } : {}),
        ...(k < came.length ? { new: { kind: "added", line: came[k] } } : {}),
      });
    }
  }

  return {
    oldLines: splitLines(oldSource),
    newLines: splitLines(newSource),
    unified,
    split,
    stats: { changes, added, removed },
  };
}

/** "1 change", "3 changes", or "No changes". */
export function describeChanges(stats: DiffStats): string {
  if (stats.changes === 0) {
    return "No changes";
  }
  return `${stats.changes} ${stats.changes === 1 ? "change" : "changes"}`;
}
