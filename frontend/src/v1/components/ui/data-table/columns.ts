import type {
  DataTableAlign,
  DataTableColumn,
  DataTableColumnPriority,
  DataTableColumnWidth,
  DataTableSortValue,
} from "./types";

/*
 * Pure helpers behind the table: column widths and alignment as classes,
 * the priority breakpoints, and the client-side sort comparison.
 */

/** Space-token widths; see `DataTableColumnWidth`. */
export const WIDTH_CLASS: Readonly<Record<DataTableColumnWidth, string>> = {
  xs: "ui:w-12",
  sm: "ui:w-24",
  md: "ui:w-40",
  lg: "ui:w-56",
  xl: "ui:w-80",
};

export const ALIGN_CLASS: Readonly<Record<DataTableAlign, string>> = {
  start: "ui:text-left",
  center: "ui:text-center",
  end: "ui:text-right",
};

/** Where a header's sort button sits, matching the cells under it. */
export const JUSTIFY_CLASS: Readonly<Record<DataTableAlign, string>> = {
  start: "ui:justify-start",
  center: "ui:justify-center",
  end: "ui:justify-end",
};

/**
 * The narrowest screen each priority shows at: the dev spec's breakpoints
 * (board 683:135, section 7: 1024, 1280, 1440; list screens stay usable to
 * 768, where only priority 1 is left).
 */
export const PRIORITY_MIN_WIDTH: Readonly<
  Record<DataTableColumnPriority, number>
> = {
  1: 0,
  2: 1024,
  3: 1280,
  4: 1440,
};

const PRIORITIES: readonly DataTableColumnPriority[] = [4, 3, 2];

/** The highest priority that shows at a screen width. */
export function priorityForWidth(width: number): DataTableColumnPriority {
  return PRIORITIES.find((p) => width >= PRIORITY_MIN_WIDTH[p]) ?? 1;
}

export function columnShows<TRow>(
  column: DataTableColumn<TRow>,
  tier: DataTableColumnPriority,
): boolean {
  return (column.priority ?? 1) <= tier;
}

/** The value a client sort compares for a row; `undefined` sorts last. */
export function sortValue<TRow>(
  column: DataTableColumn<TRow>,
  row: TRow,
): DataTableSortValue | undefined {
  const { sortKey } = column;
  if (sortKey === undefined) {
    return undefined;
  }
  const value =
    typeof sortKey === "function" ? sortKey(row) : (row[sortKey] as unknown);
  return value === null || value === undefined
    ? undefined
    : (value as DataTableSortValue);
}

const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

/**
 * Ascending order of two present values: numbers and dates by value,
 * booleans false first, strings by a numeric-aware, case-blind collator
 * ("run 2" before "run 10"). Mixed types compare as strings.
 */
export function compareSortValues(
  a: Exclude<DataTableSortValue, null>,
  b: Exclude<DataTableSortValue, null>,
): number {
  if (a instanceof Date && b instanceof Date) {
    return a.getTime() - b.getTime();
  }
  if (typeof a === "number" && typeof b === "number") {
    return a - b;
  }
  if (typeof a === "boolean" && typeof b === "boolean") {
    return Number(a) - Number(b);
  }
  return collator.compare(String(a), String(b));
}
