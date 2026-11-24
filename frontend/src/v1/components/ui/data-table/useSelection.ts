import { useMemo, useState } from "react";
import { selectionAnnouncement } from "./announce";

/*
 * Row selection, in one place, because it has three views that are easy to
 * mix up:
 * - held: what the parent controls (`selectedIds`) or the table keeps;
 * - visible: held ids present in `rows`. Without server pagination the table
 *   holds every row, so an id missing from `rows` is hidden by a filter or
 *   gone. The count, the header box and the bulk bar see only these;
 * - base: where a change starts. While `filtered` it is the held list, so a
 *   row the filter hides stays selected; otherwise the visible one, so an id
 *   whose row is gone (deleted) is dropped on the next change.
 * With server pagination every view is the held list: other pages' ids count.
 */

export type SelectionChange = Readonly<{
  next: readonly string[];
  /** What the live region says once the change shows. */
  text: string;
}>;

export type Selection = Readonly<{
  /** The held ids present in the rows (all held ids when server-paged). */
  visible: readonly string[];
  has: (id: string) => boolean;
  toggle: (id: string) => SelectionChange;
  /** Selects the page's rows, or clears them if all are selected. */
  togglePage: (pageIds: readonly string[]) => SelectionChange;
  clear: () => SelectionChange;
  /** Keeps a change: stores it when uncontrolled and reports it. */
  commit: (change: SelectionChange) => void;
}>;

export function useSelection({
  rowIds,
  controlled,
  initial,
  filtered,
  onChange,
}: Readonly<{
  /** Ids of the rows the table holds; null when server-paged. */
  rowIds: ReadonlySet<string> | null;
  controlled: readonly string[] | undefined;
  initial: readonly string[];
  filtered: boolean;
  onChange: ((ids: readonly string[]) => void) | undefined;
}>): Selection {
  const [own, setOwn] = useState<readonly string[]>(initial);
  const held = controlled ?? own;
  const visible = useMemo(
    () => (rowIds === null ? held : held.filter((id) => rowIds.has(id))),
    [rowIds, held],
  );
  const visibleSet = useMemo(() => new Set(visible), [visible]);
  const base = filtered ? held : visible;
  const count = (ids: readonly string[]): number =>
    rowIds === null ? ids.length : ids.filter((id) => rowIds.has(id)).length;

  return {
    visible,
    has: (id) => visibleSet.has(id),
    toggle: (id) => {
      const next = base.includes(id)
        ? base.filter((item) => item !== id)
        : [...base, id];
      return { next, text: selectionAnnouncement(count(next), null) };
    },
    togglePage: (pageIds) => {
      const all =
        pageIds.length > 0 && pageIds.every((id) => visibleSet.has(id));
      if (all) {
        const onPage = new Set(pageIds);
        const next = base.filter((id) => !onPage.has(id));
        return { next, text: selectionAnnouncement(count(next), null) };
      }
      const next = [...new Set([...base, ...pageIds])];
      return {
        next,
        text: selectionAnnouncement(count(next), pageIds.length),
      };
    },
    clear: () => ({ next: [], text: selectionAnnouncement(0, null) }),
    commit: ({ next }) => {
      // Always kept, so a parent that stops controlling (passes undefined
      // again) gets the last selection, not one from before it took over.
      setOwn(next);
      onChange?.(next);
    },
  };
}
