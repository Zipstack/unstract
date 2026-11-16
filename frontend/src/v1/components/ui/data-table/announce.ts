import type { DataTableSort } from "./types";

/*
 * What the table's live region says after a user sorts or selects. The
 * region is polite: it waits for the screen reader to finish, and a newer
 * message replaces an unread one.
 */

const DIRECTION_TEXT = { asc: "ascending", desc: "descending" } as const;

export function sortAnnouncement(
  sort: DataTableSort | null,
  headerOf: (columnId: string) => string,
): string {
  if (!sort) {
    return "Sort cleared";
  }
  return `Sorted by ${headerOf(sort.columnId)}, ${DIRECTION_TEXT[sort.direction]}`;
}

const count = (n: number): string => n.toLocaleString("en-US");
const rows = (n: number): string => `${count(n)} ${n === 1 ? "row" : "rows"}`;

/** "3 rows selected", or "All 25 rows on this page selected" from the header box. */
export function selectionAnnouncement(
  total: number,
  allOnPage: number | null,
): string {
  if (total === 0) {
    return "Selection cleared";
  }
  if (allOnPage !== null) {
    return `All ${rows(allOnPage)} on this page selected, ${count(total)} in total`;
  }
  return `${rows(total)} selected`;
}

/** The bulk bar's count, "2 selected". */
export const selectedText = (n: number): string => `${count(n)} selected`;
