import { expect, it } from "vitest";
import {
  computeLineDiff,
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
  expect(diff.stats).toEqual({ changes: 2, added: 3, removed: 2 });
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
  expect(diff.stats).toEqual({ changes: 1, added: 2, removed: 1 });
  expect(describeChanges(diff.stats)).toBe("1 change");
});

it("ignores a trailing newline and CRLF, so only real edits count", () => {
  const diff = diffOf("a\r\nb\r\n", "a\nb");
  expect(diff.stats.changes).toBe(0);
  expect(describeChanges(diff.stats)).toBe("No changes");
  expect(diff.oldLines).toEqual(["a", "b"]);
});

it("handles an empty side", () => {
  expect(diffOf("", "x\ny").stats).toEqual({
    changes: 1,
    added: 2,
    removed: 0,
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
  expect(DIFF_TIMEOUT_MS).toBeGreaterThan(0);
});

it("diffStats gives the counts on their own", () => {
  expect(diffStats("a\nb", "a\nc\nd")).toEqual({
    changes: 1,
    added: 2,
    removed: 1,
  });
});
