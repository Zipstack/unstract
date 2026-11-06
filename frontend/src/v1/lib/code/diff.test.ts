import { expect, it, vi } from "vitest";
import {
  computeLineDiff,
  DIFF_MAX_EDIT_LENGTH,
  DIFF_MAX_LINES,
  DIFF_TIMEOUT_MS,
  describeChanges,
  diffStats,
} from "./diff";

function diffOf(oldText: string, newText: string) {
  const diff = computeLineDiff(oldText, newText);
  if (!diff) {
    throw new Error("diff hit its limits");
  }
  return diff;
}

it("counts changes as separate runs of changed lines", () => {
  const diff = diffOf("a\nb\nc\nd\ne", "a\nB\nc\nd\nE\nF");
  expect(diff.stats).toEqual({
    changes: 2,
    added: 3,
    removed: 2,
    endingsOnly: false,
  });
  expect(describeChanges(diff.stats)).toBe("2 changes");
});

it("pairs removed and added lines side by side, padding the shorter side", () => {
  const diff = diffOf("one\nold\ntwo", "one\nnew A\nnew B\ntwo");
  expect(diff.split).toEqual([
    { old: { kind: "context", line: 0 }, new: { kind: "context", line: 0 } },
    { old: { kind: "removed", line: 1 }, new: { kind: "added", line: 1 } },
    { new: { kind: "added", line: 2 } },
    { old: { kind: "context", line: 2 }, new: { kind: "context", line: 3 } },
  ]);
  expect(diff.unified).toEqual([
    { kind: "context", oldLine: 0, newLine: 0 },
    { kind: "removed", oldLine: 1 },
    { kind: "added", newLine: 1 },
    { kind: "added", newLine: 2 },
    { kind: "context", oldLine: 2, newLine: 3 },
  ]);
  expect(diff.stats).toEqual({
    changes: 1,
    added: 2,
    removed: 1,
    endingsOnly: false,
  });
  expect(describeChanges(diff.stats)).toBe("1 change");
});

it("counts no line change for CRLF or a final newline, but says the texts differ", () => {
  const diff = diffOf("a\r\nb\r\n", "a\nb");
  expect(diff.stats.changes).toBe(0);
  expect(diff.stats.endingsOnly).toBe(true);
  expect(describeChanges(diff.stats)).toBe("Only line endings differ");
  expect(diff.oldLines).toEqual(["a", "b"]);
  expect(describeChanges(diffOf("a", "a\n").stats)).toBe(
    "Only line endings differ",
  );
  const same = diffOf("a\nb", "a\nb").stats;
  expect(same.endingsOnly).toBe(false);
  expect(describeChanges(same)).toBe("No changes");
});

it("handles an empty side", () => {
  expect(diffOf("", "x\ny").stats).toEqual({
    changes: 1,
    added: 2,
    removed: 0,
    endingsOnly: false,
  });
  expect(diffOf("x", "").split).toEqual([
    { old: { kind: "removed", line: 0 } },
  ]);
  expect(diffOf("", "").unified).toEqual([]);
});

it("gives up past its limits instead of freezing, and says so with null", () => {
  expect(
    computeLineDiff("a\nb\nc", "x\ny\nz", { maxEditLength: 1 }),
  ).toBeNull();
  expect(computeLineDiff("a\nb", "a\nB", { maxEditLength: 2 })).not.toBeNull();
});

it("by default gives up past DIFF_MAX_EDIT_LENGTH added plus removed lines", () => {
  // A still clock, so only the edit limit decides (a busy runner can take a
  // second over the larger cases).
  vi.spyOn(Date, "now").mockReturnValue(0);
  const lines = (n: number, tag: string) =>
    Array.from({ length: n }, (_, i) => `${tag}${i}`).join("\n");
  const half = DIFF_MAX_EDIT_LENGTH / 2;
  // Every line changed: 2 × n edits.
  expect(computeLineDiff(lines(half, "a"), lines(half, "b"))).not.toBeNull();
  expect(
    computeLineDiff(lines(half + 1, "a"), lines(half + 1, "b")),
  ).toBeNull();
  // An odd count pins the exact limit: one over is too many.
  expect(computeLineDiff(lines(half, "a"), lines(half + 1, "b"))).toBeNull();
});

it("by default gives up once DIFF_TIMEOUT_MS has passed", () => {
  // Each read of the clock jumps past the deadline.
  let now = 0;
  vi.spyOn(Date, "now").mockImplementation(() => {
    now += 2 * DIFF_TIMEOUT_MS;
    return now;
  });
  expect(computeLineDiff("a\nb\nc", "x\ny\nz")).toBeNull();
});

it("diffStats gives the counts on their own", () => {
  expect(diffStats("a\nb", "a\nc\nd")).toEqual({
    changes: 1,
    added: 2,
    removed: 1,
    endingsOnly: false,
  });
  // The same limits as DiffView, so the two never disagree.
  const long = Array.from({ length: 1001 }, (_, i) => `l${i}`).join("\n");
  expect(diffStats(long, `${long}\nx`)).toBeNull();
});

it("gives up on long texts even when they barely differ", () => {
  const lines = (n: number) =>
    Array.from({ length: n }, (_, i) => `line ${i}`).join("\n");
  const half = DIFF_MAX_LINES / 2;
  // One edited line: well inside the edit limit either way.
  expect(
    computeLineDiff(lines(half), `${lines(half - 1)}\nedited`),
  ).not.toBeNull();
  expect(computeLineDiff(lines(half + 1), `${lines(half)}\nedited`)).toBeNull();
});
