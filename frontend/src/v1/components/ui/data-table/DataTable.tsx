import {
  type ColumnDef,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type Row,
  useReactTable,
} from "@tanstack/react-table";
import { defaultRangeExtractor, useVirtualizer } from "@tanstack/react-virtual";
import { IconButton } from "@v1/components/ui/button";
import {
  InlineAlert,
  Skeleton,
  SkeletonBlock,
} from "@v1/components/ui/feedback";
import { RowActionMenu, RowContextMenu } from "@v1/components/ui/menu";
import { Pagination } from "@v1/components/ui/navigation";
import { Checkbox } from "@v1/components/ui/toggles";
import { cn } from "@v1/lib/cn";
import { PORTAL_CONTAINER_ID } from "@v1/lib/portal";
import { ArrowDown, ArrowUp, ChevronRight, ChevronsUpDown } from "lucide-react";
import {
  Fragment,
  type JSX,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { sortAnnouncement } from "./announce";
import { BulkBar } from "./BulkBar";
import {
  ALIGN_CLASS,
  columnShows,
  compareSortValues,
  JUSTIFY_CLASS,
  sortValue,
  WIDTH_CLASS,
} from "./columns";
import type {
  DataTableColumn,
  DataTableProps,
  DataTableSort,
  DataTableSortValue,
} from "./types";
import { pageSizeOr, useClientPage } from "./useClientPage";
import { usePriorityTier } from "./usePriorityTier";
import { type SelectionChange, useSelection } from "./useSelection";

/** Spec: 56-pixel rows (`ui:h-14`). The virtualiser's estimate and floor. */
const ROW_HEIGHT = 56;
/** `scroll="container"` renders only the rows in view past this many. */
const VIRTUALIZE_ABOVE = 50;
/** The default 25 is in the list, so the user can always go back to it. */
const TABLE_PAGE_SIZES: readonly number[] = [10, 25, 50, 100];
const MAX_LOADING_ROWS = 10;
const NO_BREAK_SPACE = " ";
const SEP = "\u0000";
const EMPTY: readonly string[] = [];
const INITIAL_VIEWPORT = { width: 0, height: ROW_HEIGHT * 12 };
/** The skeleton's three widths (dev spec section 8, as `feedback/Skeleton`). */
const SKELETON_WIDTHS = ["ui:w-full", "ui:w-[78%]", "ui:w-[46%]"] as const;

/*
 * Frames A01 (1078:936) and L10 (1252:4201) and the dev spec board
 * (683:135): a bordered card, radius 10; a 40-tall muted header in overline
 * caps; 56-tall rows (the spec; the frames draw 52) with a 1px rule; the
 * selected row in primary-muted with a 2px primary bar on its left edge; the
 * hover in accent; a failed row in the destructive token at 5% (the frames'
 * #fef2f2 has no token). `data-selected`, not `data-state`: the row is a
 * context-menu trigger, which owns `data-state`.
 */
const HEAD_CELL =
  "ui:sticky ui:top-0 ui:z-10 ui:box-border ui:h-10 ui:border-0 ui:border-b ui:border-solid ui:border-border ui:bg-muted ui:px-4 ui:py-0 ui:align-middle ui:font-sans ui:text-overline ui:font-semibold ui:text-muted-foreground ui:uppercase";
const CELL =
  "ui:box-border ui:border-0 ui:border-b ui:border-solid ui:border-border ui:px-4 ui:py-2 ui:align-middle ui:font-sans ui:text-body ui:text-foreground";
const UTILITY_CELL = "ui:w-12 ui:px-0 ui:text-center";
const ROW =
  "ui:h-14 ui:outline-none ui:focus-visible:focus-ring ui:data-[tone=failure]:bg-destructive/5 ui:data-selected:bg-primary-muted";
const ROW_HOVER =
  "ui:not-data-selected:hover:bg-accent ui:data-[tone=failure]:not-data-selected:hover:bg-destructive/10";
const SELECTED_BAR =
  "ui:relative ui:before:absolute ui:before:inset-y-0 ui:before:left-0 ui:before:w-0.5 ui:before:bg-primary ui:before:content-['']";

/** A click on these inside a row is theirs, not the row's. */
const OWN_CLICK = [
  "a",
  "button",
  "input",
  "select",
  "textarea",
  "label",
  "[contenteditable=true]",
  ...[
    "checkbox",
    "menuitem",
    "slider",
    "switch",
    "radio",
    "combobox",
    "textbox",
  ].map((role) => `[role=${role}]`),
  // The v1 Slider's track and range are plain spans inside this group.
  "[data-slot=slider]",
  // Anything else a cell wants to keep to itself.
  "[data-row-click=ignore]",
].join(", ");

function fromControl(event: MouseEvent<HTMLElement>): boolean {
  const target = event.target as Element | null;
  // React bubbles events out of portals: a click on the row menu, rendered
  // under <body>, reaches the row's handler but is not inside the row.
  if (!(target && event.currentTarget.contains(target))) {
    return true;
  }
  const control = target?.closest?.(OWN_CLICK);
  return (
    control !== null &&
    control !== undefined &&
    control !== event.currentTarget &&
    event.currentTarget.contains(control)
  );
}

function nextSort(
  current: DataTableSort | null,
  columnId: string,
): DataTableSort | null {
  if (current?.columnId !== columnId) {
    return { columnId, direction: "asc" };
  }
  return current.direction === "asc" ? { columnId, direction: "desc" } : null;
}

const sortKeyOf = (sort: DataTableSort | null): string =>
  sort ? `${sort.columnId}:${sort.direction}` : "";

const visibleIn = (
  ids: readonly string[],
  rowIds: ReadonlySet<string>,
): readonly string[] => ids.filter((id) => rowIds.has(id));

const SORT_ICON = { asc: ArrowUp, desc: ArrowDown } as const;
const ARIA_SORT = { asc: "ascending", desc: "descending" } as const;

/**
 * The one table for every list: typed columns, single-column sort, client or
 * server pagination, row selection with a bulk bar, in-place expansion, a row
 * click target and row actions, on TanStack Table. See README.md.
 */
export function DataTable<TRow>({
  label,
  columns,
  rows,
  getRowId,
  getRowLabel,
  sort: sortProp,
  defaultSort = null,
  onSortChange,
  pagination,
  selectable = false,
  selectedIds: selectedProp,
  defaultSelectedIds = [],
  onSelectionChange,
  bulkActions,
  renderExpanded,
  canExpand,
  defaultExpandedIds = [],
  onRowClick,
  rowActions,
  getRowTone,
  loading = false,
  loadingRows,
  error,
  filtered = false,
  toolbar,
  empty,
  noResults,
  footer,
  scroll = "page",
  className,
}: DataTableProps<TRow>): JSX.Element {
  const server = pagination?.mode === "server";
  const clientPaged = pagination?.mode === "client";
  const tier = usePriorityTier();
  const detailIdBase = useId();

  // ── Sort ──────────────────────────────────────────────────────────────
  // Always kept, so a parent that stops controlling (passes undefined again)
  // gets the last sort, not one from before it took over.
  const [ownSort, setOwnSort] = useState<DataTableSort | null>(defaultSort);
  const sort = sortProp === undefined ? ownSort : sortProp;
  const canSort = (column: DataTableColumn<TRow>): boolean =>
    column.sortKey !== undefined && (!server || onSortChange !== undefined);

  // ── Selection ─────────────────────────────────────────────────────────
  const rowIds = useMemo(
    () => (server ? null : new Set(rows.map(getRowId))),
    [server, rows, getRowId],
  );
  const selection = useSelection({
    rowIds,
    controlled: selectedProp,
    initial: defaultSelectedIds,
    filtered,
    onChange: onSelectionChange,
  });
  const selectedList = selectable ? selection.visible : EMPTY;

  // ── Expansion and client paging ───────────────────────────────────────
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(defaultExpandedIds.map((id) => [id, true])),
  );
  const page = useClientPage({
    rowCount: rows.length,
    defaultPageSize: clientPaged ? pagination.defaultPageSize : undefined,
    filtered,
    resetKey: clientPaged ? pagination.resetKey : undefined,
    sortKey: sortKeyOf(sort),
  });

  // ── What the live region says ─────────────────────────────────────────
  // A change is announced once it shows, so a controlled parent that
  // ignores it announces nothing. A repeat of the same words would not be
  // read again, so every other message carries a no-break space.
  const [announcement, setAnnouncement] = useState({ text: "", flip: false });
  const pending = useRef<{ key: string; text: string } | null>(null);
  const shownKey = `${sortKeyOf(sort)}|${selectedList.join(SEP)}`;
  useEffect(() => {
    const due = pending.current;
    if (due !== null && due.key === shownKey) {
      pending.current = null;
      setAnnouncement((last) => ({ text: due.text, flip: !last.flip }));
    }
  }, [shownKey]);

  const columnDefs = useMemo<ColumnDef<TRow, DataTableSortValue | undefined>[]>(
    () =>
      columns.map((column) => ({
        id: column.id,
        accessorFn: (row: TRow) => sortValue(column, row),
        enableSorting: column.sortKey !== undefined,
        sortUndefined: "last",
        sortingFn: (a, b, id) =>
          compareSortValues(
            a.getValue(id) as Exclude<DataTableSortValue, null>,
            b.getValue(id) as Exclude<DataTableSortValue, null>,
          ),
      })),
    [columns],
  );

  const columnVisibility = useMemo(
    () =>
      Object.fromEntries(
        columns.map((column) => [column.id, columnShows(column, tier)]),
      ),
    [columns, tier],
  );

  const rowSelection = useMemo(
    () => Object.fromEntries(selectedList.map((id) => [id, true])),
    [selectedList],
  );

  const sortColumn = sort?.columnId;
  const sortDirection = sort?.direction;
  const sorting = useMemo(
    () =>
      sortColumn === undefined
        ? []
        : [{ id: sortColumn, desc: sortDirection === "desc" }],
    [sortColumn, sortDirection],
  );
  const paginationState = useMemo(
    () => ({ pageIndex: page.pageIndex, pageSize: page.pageSize }),
    [page.pageIndex, page.pageSize],
  );

  const table = useReactTable<TRow>({
    data: rows as TRow[],
    columns: columnDefs,
    getRowId: (row) => getRowId(row),
    state: {
      sorting,
      rowSelection,
      expanded,
      columnVisibility,
      pagination: paginationState,
    },
    // The component owns every piece of state, so TanStack must not reset
    // any of it: its auto-reset sets internal state, which re-renders, and
    // with client pagination that looped.
    autoResetAll: false,
    enableRowSelection: selectable,
    getRowCanExpand: (row) =>
      renderExpanded !== undefined && (canExpand?.(row.original) ?? true),
    manualSorting: server,
    manualPagination: !clientPaged,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: server ? undefined : getSortedRowModel(),
    getPaginationRowModel: clientPaged ? getPaginationRowModel() : undefined,
  });

  const pageRows = table.getRowModel().rows;
  const shownColumns = columns.filter((column) => columnVisibility[column.id]);
  const headerOf = (columnId: string): string =>
    columns.find((column) => column.id === columnId)?.header ?? columnId;

  const changeSort = (columnId: string): void => {
    const next = nextSort(sort, columnId);
    setOwnSort(next);
    onSortChange?.(next);
    // A new order starts on page 1: a client table resets itself when the
    // shown sort changes (useClientPage); a server table asks its parent.
    if (server && pagination.page !== 1) {
      pagination.onPageChange(1);
    }
    pending.current = {
      key: `${sortKeyOf(next)}|${selectedList.join(SEP)}`,
      text: sortAnnouncement(next, headerOf),
    };
  };

  const commitSelection = (change: SelectionChange): void => {
    selection.commit(change);
    const shown =
      rowIds === null ? change.next : visibleIn(change.next, rowIds);
    pending.current = {
      key: `${sortKeyOf(sort)}|${shown.join(SEP)}`,
      text: change.text,
    };
  };

  const pageIds = pageRows.map((row) => row.id);
  const pageSelectedCount = pageIds.filter((id) => selection.has(id)).length;
  const allOnPage = pageIds.length > 0 && pageSelectedCount === pageIds.length;
  const someOnPage = pageSelectedCount > 0 && !allOnPage;

  const toggleRow = (id: string): void => {
    commitSelection(selection.toggle(id));
  };
  const togglePage = (): void => {
    commitSelection(selection.togglePage(pageIds));
  };
  const clearSelection = (): void => {
    commitSelection(selection.clear());
  };

  const isOpen = (row: Row<TRow>): boolean =>
    row.getIsExpanded() && row.getCanExpand();

  const toggleExpanded = (id: string, open?: boolean): void => {
    setExpanded((last) => ({ ...last, [id]: open ?? !last[id] }));
  };

  // ── Roving focus: one row is in the tab order; arrows move it ────────
  const expandable = renderExpanded !== undefined;
  const interactive =
    onRowClick !== undefined ||
    selectable ||
    expandable ||
    rowActions !== undefined;
  const [activeId, setActiveId] = useState<string | null>(null);
  const active = pageIds.includes(activeId ?? "")
    ? activeId
    : (pageIds[0] ?? null);
  const activeIndex = active === null ? -1 : pageIds.indexOf(active);
  const rowElements = useRef(new Map<string, HTMLTableRowElement>());
  const focusTarget = useRef<string | null>(null);

  // ── Virtualisation (container scroll only) ───────────────────────────
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtual =
    scroll === "container" && !loading && pageRows.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    count: pageRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    getItemKey: (index) => pageRows[index]?.id ?? index,
    // A row and its expanded detail are measured together; never below a
    // row, so a layout that reports no height (tests) still windows.
    measureElement: (element) =>
      Math.max(element.getBoundingClientRect().height, ROW_HEIGHT),
    overscan: 8,
    // The active row always renders, so Tab can reach the body and a
    // focused row is not unmounted when it scrolls out of view.
    rangeExtractor: (range) => {
      const indexes = defaultRangeExtractor(range);
      return activeIndex < 0 || indexes.includes(activeIndex)
        ? indexes
        : [...indexes, activeIndex].sort((a, b) => a - b);
    },
    enabled: virtual,
    initialRect: INITIAL_VIEWPORT,
  });

  useEffect(() => {
    const id = focusTarget.current;
    if (id === null) {
      return;
    }
    const element = rowElements.current.get(id);
    if (element) {
      focusTarget.current = null;
      element.focus();
    }
  });

  // A container table opens a new page or order at the top.
  const viewKey = `${server ? pagination.page : page.pageIndex}|${sortKeyOf(sort)}`;
  const shownView = useRef(viewKey);
  useEffect(() => {
    if (shownView.current === viewKey) {
      return;
    }
    shownView.current = viewKey;
    if (scroll === "container" && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [viewKey, scroll]);

  // ── Focus that would drop to <body> ───────────────────────────────────
  // When the focused control unmounts (Clear selection, Retry, a deleted
  // row, the skeleton replacing the body), focus goes to the active row, or
  // to the header when there are no rows, so a screen reader keeps its place.
  const lastFocused = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const doc = root.ownerDocument;
    const inside = (node: EventTarget | null): boolean =>
      node instanceof Node &&
      (root.contains(node) ||
        // The row menu is portalled; focus there still belongs to the table.
        doc.getElementById(PORTAL_CONTAINER_ID)?.contains(node) === true);
    const onFocusIn = (event: FocusEvent): void => {
      if (root.contains(event.target as Node)) {
        lastFocused.current = event.target as HTMLElement;
      }
    };
    const onFocusOut = (event: FocusEvent): void => {
      if (event.relatedTarget !== null && !inside(event.relatedTarget)) {
        lastFocused.current = null;
      }
    };
    const onPointerDown = (event: PointerEvent): void => {
      if (!inside(event.target)) {
        lastFocused.current = null;
      }
    };
    root.addEventListener("focusin", onFocusIn);
    root.addEventListener("focusout", onFocusOut);
    doc.addEventListener("pointerdown", onPointerDown);
    return () => {
      root.removeEventListener("focusin", onFocusIn);
      root.removeEventListener("focusout", onFocusOut);
      doc.removeEventListener("pointerdown", onPointerDown);
    };
  }, []);
  useLayoutEffect(() => {
    const last = lastFocused.current;
    const root = rootRef.current;
    if (!last || last.isConnected || !root) {
      return;
    }
    const now = root.ownerDocument.activeElement;
    if (now && now !== root.ownerDocument.body) {
      lastFocused.current = null;
      return;
    }
    const row = active === null ? undefined : rowElements.current.get(active);
    const fallback =
      (interactive ? row : undefined) ??
      root.querySelector<HTMLElement>(
        "thead button:not(:disabled), thead [role=checkbox]:not(:disabled)",
      );
    if (fallback) {
      fallback.focus();
    } else {
      lastFocused.current = null;
    }
  });

  const moveTo = (index: number): void => {
    const target = pageRows[Math.min(Math.max(index, 0), pageRows.length - 1)];
    if (!target) {
      return;
    }
    setActiveId(target.id);
    if (virtual) {
      virtualizer.scrollToIndex(pageRows.indexOf(target));
    }
    const element = rowElements.current.get(target.id);
    if (element) {
      element.focus();
    } else {
      // Not rendered yet: the effect focuses it once it is.
      focusTarget.current = target.id;
    }
  };

  const onRowKeyDown = (
    event: KeyboardEvent<HTMLTableRowElement>,
    row: Row<TRow>,
    index: number,
  ): void => {
    if (
      event.target !== event.currentTarget ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey
    ) {
      return;
    }
    const rowCanExpand = row.getCanExpand();
    const go = (target: number): boolean => {
      moveTo(target);
      return true;
    };
    // Each returns false when the key does nothing here, so the browser
    // keeps it (Space still scrolls a table without selection).
    const keys: Record<string, () => boolean> = {
      ArrowDown: () => go(index + 1),
      ArrowUp: () => go(index - 1),
      Home: () => go(0),
      End: () => go(pageRows.length - 1),
      Enter: () => {
        if (onRowClick) {
          onRowClick(row.original);
        } else if (rowCanExpand) {
          toggleExpanded(row.id);
        }
        return onRowClick !== undefined || rowCanExpand;
      },
      " ": () => {
        if (selectable) {
          toggleRow(row.id);
        }
        return selectable;
      },
      ArrowRight: () => {
        if (rowCanExpand) {
          toggleExpanded(row.id, true);
        }
        return rowCanExpand;
      },
      ArrowLeft: () => {
        if (rowCanExpand) {
          toggleExpanded(row.id, false);
        }
        return rowCanExpand;
      },
    };
    if (keys[event.key]?.()) {
      event.preventDefault();
    }
  };

  // ── Row numbers for a virtualised table ───────────────────────────────
  // aria-rowindex counts the header (1) and every open detail row, so a
  // screen reader's position matches the rows it can reach.
  const ariaRowIndex: number[] = [];
  let openDetails = 0;
  if (virtual) {
    pageRows.forEach((row, i) => {
      ariaRowIndex[i] = i + 2 + openDetails;
      if (isOpen(row) && renderExpanded) {
        openDetails += 1;
      }
    });
  }

  // ── Layout ────────────────────────────────────────────────────────────
  const columnCount =
    shownColumns.length +
    (selectable ? 1 : 0) +
    (expandable ? 1 : 0) +
    (rowActions ? 1 : 0);
  const pageSize = server ? pagination.pageSize : page.pageSize;
  const skeletonRows = Math.min(
    pageSizeOr(loadingRows, pagination ? pageSize : 5),
    MAX_LOADING_ROWS,
  );

  const renderRow = (row: Row<TRow>, index: number): ReactNode => {
    const isSelected = row.getIsSelected();
    const isExpanded = isOpen(row);
    const tone = getRowTone?.(row.original) ?? "default";
    const rowLabel = getRowLabel(row.original);
    const isActive = interactive && row.id === active;
    const controlTab = interactive && !isActive ? -1 : undefined;
    const detailId = `${detailIdBase}-detail-${index}`;
    const actions = rowActions?.(row.original);
    // Cells as data, so the first can carry the selected bar.
    const cells: { key: string; className: string; content: ReactNode }[] = [];
    if (selectable) {
      cells.push({
        key: "select",
        className: UTILITY_CELL,
        content: (
          <div className="ui:flex ui:items-center ui:justify-center">
            <Checkbox
              checked={isSelected}
              onCheckedChange={() => toggleRow(row.id)}
              aria-label={`Select ${rowLabel}`}
              tabIndex={controlTab}
            />
          </div>
        ),
      });
    }
    if (expandable) {
      cells.push({
        key: "expand",
        className: UTILITY_CELL,
        content: row.getCanExpand() ? (
          <IconButton
            icon={ChevronRight}
            aria-label={`Details for ${rowLabel}`}
            aria-expanded={isExpanded}
            aria-controls={isExpanded ? detailId : undefined}
            tabIndex={controlTab}
            onClick={() => toggleExpanded(row.id)}
            className={cn(
              "ui:[&>svg]:transition-transform ui:motion-reduce:[&>svg]:transition-none",
              isExpanded && "ui:[&>svg]:rotate-90",
            )}
          />
        ) : null,
      });
    }
    for (const column of shownColumns) {
      cells.push({
        key: column.id,
        className: ALIGN_CLASS[column.align ?? "start"],
        content: column.cell(row.original, {
          tabIndex: controlTab,
          active: isActive,
        }),
      });
    }
    if (actions) {
      cells.push({
        key: "actions",
        className: "ui:px-2 ui:text-right",
        content: (
          <div className="ui:inline-flex ui:items-center">
            <RowActionMenu
              label={`Actions for ${rowLabel}`}
              actions={actions}
              tabIndex={controlTab}
            />
          </div>
        ),
      });
    }
    const tr = (
      <tr
        ref={(element) => {
          if (element) {
            rowElements.current.set(row.id, element);
          } else {
            rowElements.current.delete(row.id);
          }
        }}
        data-slot="data-table-row"
        data-selected={isSelected ? "" : undefined}
        data-tone={tone === "failure" ? "failure" : undefined}
        aria-rowindex={virtual ? ariaRowIndex[index] : undefined}
        tabIndex={interactive ? (isActive ? 0 : -1) : undefined}
        className={cn(ROW, ROW_HOVER, onRowClick && "ui:cursor-pointer")}
        onFocus={() => {
          if (interactive && activeId !== row.id) {
            setActiveId(row.id);
          }
        }}
        onClick={
          onRowClick
            ? (event) => {
                if (!fromControl(event)) {
                  onRowClick(row.original);
                }
              }
            : undefined
        }
        onKeyDown={
          interactive ? (event) => onRowKeyDown(event, row, index) : undefined
        }
      >
        {cells.map(({ key, className: cellClass, content }, i) => (
          <td
            key={key}
            className={cn(
              CELL,
              cellClass,
              i === 0 && isSelected && SELECTED_BAR,
            )}
          >
            {content}
          </td>
        ))}
      </tr>
    );
    return (
      <Fragment key={row.id}>
        {actions ? <RowContextMenu actions={actions}>{tr}</RowContextMenu> : tr}
        {isExpanded && renderExpanded && (
          <tr
            data-slot="data-table-expanded"
            aria-rowindex={virtual ? ariaRowIndex[index] + 1 : undefined}
          >
            <td
              id={detailId}
              colSpan={columnCount}
              className={cn(CELL, "ui:bg-card ui:py-3")}
            >
              {renderExpanded(row.original)}
            </td>
          </tr>
        )}
      </Fragment>
    );
  };

  const message = (content: ReactNode, slot: string): ReactNode => (
    <tbody>
      <tr data-slot={slot}>
        <td
          colSpan={columnCount}
          className={cn(
            CELL,
            "ui:border-b-0 ui:py-12 ui:text-center ui:text-muted-foreground",
          )}
        >
          {content}
        </td>
      </tr>
    </tbody>
  );

  let body: ReactNode;
  if (loading) {
    body = (
      <tbody aria-hidden data-slot="data-table-skeleton">
        {Array.from({ length: skeletonRows }, (_, r) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows.
          <tr key={r} className="ui:h-14">
            {Array.from({ length: columnCount }, (_, c) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder cells.
              <td key={c} className={CELL}>
                <SkeletonBlock
                  className={cn(
                    "ui:h-3",
                    SKELETON_WIDTHS[(r + c) % SKELETON_WIDTHS.length],
                  )}
                />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    );
  } else if (pageRows.length === 0) {
    body = error
      ? null
      : filtered
        ? message(
            noResults ?? "No results match your search or filters.",
            "data-table-no-results",
          )
        : message(empty ?? "Nothing here yet.", "data-table-empty");
  } else if (virtual) {
    // The rendered rows need not be contiguous (the active row is kept), so
    // a spacer fills every gap, then the rest of the list.
    const parts: ReactNode[] = [];
    let end = 0;
    for (const item of virtualizer.getVirtualItems()) {
      if (item.start > end) {
        parts.push(
          <Spacer
            key={`gap:${item.key}`}
            height={item.start - end}
            columns={columnCount}
          />,
        );
      }
      parts.push(
        <tbody
          key={`row:${item.key}`}
          data-index={item.index}
          ref={virtualizer.measureElement}
        >
          {renderRow(pageRows[item.index], item.index)}
        </tbody>,
      );
      end = item.end;
    }
    const rest = virtualizer.getTotalSize() - end;
    if (rest > 0) {
      parts.push(<Spacer key="tail" height={rest} columns={columnCount} />);
    }
    body = parts;
  } else {
    body = <tbody>{pageRows.map((row, index) => renderRow(row, index))}</tbody>;
  }

  const header = (
    <thead>
      <tr aria-rowindex={virtual ? 1 : undefined}>
        {selectable && (
          <th scope="col" className={cn(HEAD_CELL, UTILITY_CELL)}>
            <div className="ui:flex ui:items-center ui:justify-center">
              <Checkbox
                checked={someOnPage ? "indeterminate" : allOnPage}
                onCheckedChange={togglePage}
                aria-label="Select all rows on this page"
                disabled={loading || pageIds.length === 0}
              />
            </div>
          </th>
        )}
        {expandable && (
          <th scope="col" className={cn(HEAD_CELL, "ui:w-12")}>
            <span className="ui:sr-only">Details</span>
          </th>
        )}
        {shownColumns.map((column) => (
          <HeaderCell
            key={column.id}
            column={column}
            sortable={canSort(column)}
            sorted={sortColumn === column.id ? sortDirection : undefined}
            onSort={() => changeSort(column.id)}
          />
        ))}
        {rowActions && (
          <th scope="col" className={cn(HEAD_CELL, "ui:w-14")}>
            <span className="ui:sr-only">Actions</span>
          </th>
        )}
      </tr>
    </thead>
  );

  const selectedCount = selectedList.length;
  const totalRows = server ? pagination.total : rows.length;

  return (
    <div
      ref={rootRef}
      data-slot="data-table"
      className={cn(
        "ui:flex ui:min-h-0 ui:flex-col ui:gap-3 ui:font-sans",
        className,
      )}
    >
      {toolbar && <div data-slot="data-table-toolbar">{toolbar}</div>}
      {selectable && selectedCount > 0 && (
        <BulkBar label={label} count={selectedCount} onClear={clearSelection}>
          {bulkActions?.({
            selectedIds: selectedList,
            selectedRows: rows.filter((row) => selection.has(getRowId(row))),
            clearSelection,
          })}
        </BulkBar>
      )}
      {error && (
        <InlineAlert kind="error" title={error.title} onRetry={error.onRetry}>
          {error.message}
        </InlineAlert>
      )}
      <div
        ref={scrollRef}
        data-slot="data-table-frame"
        className={cn(
          "ui:box-border ui:rounded-lg ui:border ui:border-solid ui:border-border ui:bg-card ui:shadow-sm",
          scroll === "container"
            ? "ui:min-h-0 ui:flex-1 ui:overflow-auto"
            : "ui:overflow-clip",
        )}
      >
        <table
          aria-label={label}
          aria-rowcount={
            virtual ? pageRows.length + openDetails + 1 : undefined
          }
          className="ui:w-full ui:table-fixed ui:border-separate ui:border-spacing-0"
        >
          {header}
          {body}
        </table>
      </div>
      {loading && (
        <Skeleton label={`Loading ${label}`} className="ui:sr-only" />
      )}
      {(footer || pagination) && (
        <div
          data-slot="data-table-footer"
          className="ui:flex ui:flex-col ui:gap-2"
        >
          {footer}
          {pagination && (
            <Pagination
              aria-label={`${label} pages`}
              page={server ? pagination.page : page.pageIndex + 1}
              pageSize={pageSize}
              total={totalRows}
              pageSizeOptions={pagination.pageSizeOptions ?? TABLE_PAGE_SIZES}
              onPageChange={
                server
                  ? pagination.onPageChange
                  : (next) => page.setPageIndex(next - 1)
              }
              onPageSizeChange={
                server ? pagination.onPageSizeChange : page.setPageSize
              }
            />
          )}
        </div>
      )}
      <output className="ui:sr-only" data-slot="data-table-status">
        {announcement.text}
        {announcement.flip ? NO_BREAK_SPACE : ""}
      </output>
    </div>
  );
}

function Spacer({
  height,
  columns,
}: Readonly<{ height: number; columns: number }>): JSX.Element {
  return (
    <tbody aria-hidden data-slot="data-table-spacer">
      <tr>
        <td
          colSpan={columns}
          style={{ "--data-table-gap": `${height}px` }}
          className="ui:h-(--data-table-gap) ui:border-0 ui:p-0"
        />
      </tr>
    </tbody>
  );
}

function HeaderCell<TRow>({
  column,
  sortable,
  sorted,
  onSort,
}: Readonly<{
  column: DataTableColumn<TRow>;
  sortable: boolean;
  sorted: "asc" | "desc" | undefined;
  onSort: () => void;
}>): JSX.Element {
  const align = column.align ?? "start";
  const Icon = sorted ? SORT_ICON[sorted] : ChevronsUpDown;
  return (
    <th
      scope="col"
      aria-sort={sorted ? ARIA_SORT[sorted] : undefined}
      className={cn(
        HEAD_CELL,
        ALIGN_CLASS[align],
        column.width && WIDTH_CLASS[column.width],
      )}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          className={cn(
            "ui:inline-flex ui:w-full ui:cursor-pointer ui:items-center ui:gap-1 ui:rounded-sm ui:border-0 ui:bg-transparent ui:p-0 ui:font-sans ui:text-overline ui:font-semibold ui:text-muted-foreground ui:uppercase ui:outline-none ui:hover:text-foreground ui:focus-visible:focus-ring",
            JUSTIFY_CLASS[align],
            sorted && "ui:text-foreground",
          )}
        >
          {column.header}
          <Icon
            aria-hidden
            className={cn(
              "ui:size-3.5 ui:shrink-0",
              !sorted && "ui:opacity-60",
            )}
          />
        </button>
      ) : (
        column.header
      )}
    </th>
  );
}
