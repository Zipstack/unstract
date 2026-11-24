import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  selectedText,
  selectionAnnouncement,
  sortAnnouncement,
} from "./announce";
import {
  columnShows,
  compareSortValues,
  PRIORITY_MIN_WIDTH,
  priorityForWidth,
  sortValue,
} from "./columns";
import type { DataTableColumn } from "./types";
import { usePriorityTier } from "./usePriorityTier";

type R = { name: string; runs: number | null };
const byName: DataTableColumn<R> = {
  id: "name",
  header: "Name",
  sortKey: "name",
  cell: (r) => r.name,
};

describe("priority breakpoints", () => {
  it("are the dev spec's 1024, 1280 and 1440", () => {
    expect(PRIORITY_MIN_WIDTH).toEqual({ 1: 0, 2: 1024, 3: 1280, 4: 1440 });
  });

  it.each([
    [320, 1],
    [1023, 1],
    [1024, 2],
    [1279, 2],
    [1280, 3],
    [1439, 3],
    [1440, 4],
    [2560, 4],
  ] as const)("a %ipx screen shows priority %i and below", (width, tier) => {
    expect(priorityForWidth(width)).toBe(tier);
  });

  it("shows a column without a priority at every width", () => {
    expect(columnShows(byName, 1)).toBe(true);
    expect(columnShows({ ...byName, priority: 3 }, 2)).toBe(false);
    expect(columnShows({ ...byName, priority: 3 }, 3)).toBe(true);
  });

  it("shows every column where the screen cannot be measured", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => usePriorityTier());
    expect(result.current).toBe(4);
  });
});

describe("client sort values", () => {
  it("reads a field or calls a function, and treats null as missing", () => {
    expect(sortValue(byName, { name: "a", runs: 1 })).toBe("a");
    const runs: DataTableColumn<R> = { ...byName, sortKey: (r) => r.runs };
    expect(sortValue(runs, { name: "a", runs: 3 })).toBe(3);
    expect(sortValue(runs, { name: "a", runs: null })).toBeUndefined();
    expect(
      sortValue({ ...byName, sortKey: undefined }, { name: "a", runs: 1 }),
    ).toBeUndefined();
  });

  it("compares numbers, dates and booleans by value, where text order disagrees", () => {
    // Each pair sorts the other way as text.
    expect(compareSortValues(1.5, 1.25)).toBeGreaterThan(0);
    expect(compareSortValues(-1, -2)).toBeGreaterThan(0);
    expect(compareSortValues(100, 20)).toBeGreaterThan(0);
    // Mon 2 Feb 2026 after Sat 1 Feb 2025; as text "Mon…" sorts before "Sat…".
    expect(
      compareSortValues(new Date(2026, 1, 2), new Date(2025, 1, 1)),
    ).toBeGreaterThan(0);
    expect(compareSortValues(false, true)).toBeLessThan(0);
    expect(compareSortValues(true, true)).toBe(0);
  });

  it("treats NaN and an invalid date as missing", () => {
    type N = { n: number; d: Date };
    const byN: DataTableColumn<N> = {
      id: "n",
      header: "N",
      sortKey: "n",
      cell: () => null,
    };
    const byD: DataTableColumn<N> = {
      id: "d",
      header: "D",
      sortKey: "d",
      cell: () => null,
    };
    expect(sortValue(byN, { n: Number.NaN, d: new Date() })).toBeUndefined();
    expect(sortValue(byD, { n: 1, d: new Date("nope") })).toBeUndefined();
    expect(sortValue(byN, { n: 0, d: new Date() })).toBe(0);
  });

  it("only accepts row fields that hold a sortable value", () => {
    type O = { name: string; owner: { id: string } };
    const ok: DataTableColumn<O> = {
      id: "n",
      header: "N",
      sortKey: "name",
      cell: () => null,
    };
    const bad: DataTableColumn<O> = {
      id: "o",
      header: "O",
      // @ts-expect-error an object field cannot be compared
      sortKey: "owner",
      cell: () => null,
    };
    expect([ok.sortKey, bad.sortKey]).toEqual(["name", "owner"]);
  });

  it("compares text case-blind and numeric-aware", () => {
    expect(compareSortValues("run 2", "run 10")).toBeLessThan(0);
    expect(compareSortValues("Alpha", "alpha")).toBe(0);
    expect(compareSortValues("b", "A")).toBeGreaterThan(0);
  });
});

describe("announcements", () => {
  const headerOf = (id: string) => (id === "name" ? "Name" : id);

  it("says the sorted column and direction, or that the sort is off", () => {
    expect(
      sortAnnouncement({ columnId: "name", direction: "asc" }, headerOf),
    ).toBe("Sorted by Name, ascending");
    expect(
      sortAnnouncement({ columnId: "name", direction: "desc" }, headerOf),
    ).toBe("Sorted by Name, descending");
    expect(sortAnnouncement(null, headerOf)).toBe("Sort cleared");
  });

  it("says the selection count", () => {
    expect(selectionAnnouncement(0, null)).toBe("Selection cleared");
    expect(selectionAnnouncement(1, null)).toBe("1 row selected");
    expect(selectionAnnouncement(1200, null)).toBe("1,200 rows selected");
    expect(selectionAnnouncement(30, 25)).toBe(
      "All 25 rows on this page selected, 30 in total",
    );
    expect(selectedText(2)).toBe("2 selected");
  });
});
