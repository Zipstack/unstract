import type { MenuAction } from "@v1/components/ui/menu";
import type { ReactNode } from "react";

/*
 * The public contract of the data table (P1-T11). P2-T04 (resource list
 * pages), P2-T07 (logs console) and P9-T10 (API Hub administration) build on
 * it, so a change here is a change to theirs: add, do not rename.
 */

/** What a client-side sort compares. `null` and `undefined` sort last both ways. */
export type DataTableSortValue = string | number | boolean | Date | null;

/** The row fields a client sort can compare directly. */
export type DataTableSortField<TRow> = {
  [K in keyof TRow]-?: TRow[K] extends DataTableSortValue | undefined
    ? K
    : never;
}[keyof TRow] &
  string;

export type DataTableAlign = "start" | "center" | "end";

/**
 * Column width on the fixed table layout. Columns without one share what is
 * left. `xs` 48, `sm` 96, `md` 160, `lg` 224, `xl` 320 (space tokens).
 */
export type DataTableColumnWidth = "xs" | "sm" | "md" | "lg" | "xl";

/**
 * Which columns stay as the screen narrows, at the dev spec's breakpoints
 * (board 683:135, section 7): 1 always shows, 2 needs 1024 or wider, 3 needs
 * 1280, 4 needs 1440. Pages set priorities; the table owns the breakpoints.
 */
export type DataTableColumnPriority = 1 | 2 | 3 | 4;

/**
 * What a cell renderer gets besides its row. Only one row is in the tab order
 * (the active one; arrows move it): in the others `tabIndex` is -1.
 */
export type DataTableCellContext = Readonly<{
  /** Put it on any link or button in the cell. */
  tabIndex: -1 | undefined;
  /** The row is the one in the tab order. */
  active: boolean;
}>;

export type DataTableColumn<TRow> = Readonly<{
  /** Unique within the table; what `DataTableSort.columnId` names. */
  id: string;
  /** Header text, and the column's accessible name. Drawn in overline caps. */
  header: string;
  /**
   * The cell's content. A link or button in it should take
   * `context.tabIndex`, so it leaves the tab order with its row, as the
   * table's own controls do.
   */
  cell: (row: TRow, context: DataTableCellContext) => ReactNode;
  /**
   * Makes the column sortable. With client sorting, the table compares this
   * field of the row (one holding a `DataTableSortValue`), or what the
   * function returns; `NaN` and an invalid date count as missing. With
   * server pagination the table only reports the sort through
   * `onSortChange`, which is then required, and the page refetches.
   */
  sortKey?: DataTableSortField<TRow> | ((row: TRow) => DataTableSortValue);
  /** Default 1 (always shown). */
  priority?: DataTableColumnPriority;
  /** Default "start". Numbers go "end". */
  align?: DataTableAlign;
  width?: DataTableColumnWidth;
}>;

export type DataTableSortDirection = "asc" | "desc";

export type DataTableSort = Readonly<{
  columnId: string;
  direction: DataTableSortDirection;
}>;

/** A row's tint. `failure` marks a row whose last run failed or is stuck. */
export type DataTableRowTone = "default" | "failure";

/**
 * Pagination, chosen per table. `client` pages the rows it was given; `server`
 * shows the page the parent loaded, and the parent loads another on
 * `onPageChange`. Without pagination every row renders (virtualised past
 * 50 rows when `scroll="container"`). Either way a sort change goes back to
 * page 1.
 */
export type DataTablePagination =
  | Readonly<{
      mode: "client";
      /** The starting page size; default 25. The user can change it. */
      defaultPageSize?: number;
      /**
       * Back to page 1 whenever this changes: pass the search text or the
       * filters. The page also resets when `filtered` flips.
       */
      resetKey?: string | number;
      /** Default 10, 25, 50 and 100. */
      pageSizeOptions?: readonly number[];
    }>
  | Readonly<{
      mode: "server";
      /** The current page, from 1. */
      page: number;
      pageSize: number;
      /** Rows across every page. */
      total: number;
      onPageChange: (page: number) => void;
      onPageSizeChange?: (pageSize: number) => void;
      pageSizeOptions?: readonly number[];
    }>;

/** What the bulk bar's actions act on. */
export type DataTableBulkContext<TRow> = Readonly<{
  selectedIds: readonly string[];
  /** The selected rows the table holds (with server pagination, those loaded). */
  selectedRows: readonly TRow[];
  clearSelection: () => void;
}>;

/**
 * One entry in a row's action menu (the kebab at the row's end): P1-T09's
 * `MenuAction` (`id`, `label`, `onSelect`, and optionally `disabled`,
 * `destructive`, `icon`, `shortcut`, `description`, `loading`, `group`).
 * Destructive actions go last, after a separator.
 */
export type DataTableRowAction = MenuAction;

export type DataTableError = Readonly<{
  title: string;
  /** The plain-language cause. */
  message?: ReactNode;
  onRetry?: () => void;
}>;

export type DataTableProps<TRow> = Readonly<{
  /**
   * Names the table for assistive technology ("API deployments"), and from
   * it the bulk bar ("Bulk actions for API deployments") and the pagination
   * ("API deployments pages"). Unique on the page: two tables with one label
   * would give two landmarks the same name.
   */
  label: string;
  columns: readonly DataTableColumn<TRow>[];
  rows: readonly TRow[];
  getRowId: (row: TRow) => string;
  /**
   * The row's name, read in its controls' accessible names ("Select
   * invoice-parser", "Actions for invoice-parser").
   */
  getRowLabel: (row: TRow) => string;

  /**
   * Sorting: controlled with `sort` (`null` for no sort), else `defaultSort`
   * starts it. With server pagination, headers sort only when
   * `onSortChange` is given. The sort is announced once it shows, so a
   * parent that ignores a change announces nothing.
   */
  sort?: DataTableSort | null;
  defaultSort?: DataTableSort | null;
  onSortChange?: (sort: DataTableSort | null) => void;

  pagination?: DataTablePagination;

  /** Adds the checkbox column and the bulk bar. */
  selectable?: boolean;
  /**
   * Controlled selection; leave out to let the table hold it. Ignored unless
   * `selectable`.
   */
  selectedIds?: readonly string[];
  /** Uncontrolled selection's starting rows. */
  defaultSelectedIds?: readonly string[];
  onSelectionChange?: (ids: readonly string[]) => void;
  /** The bulk bar's actions, shown while any row is selected. */
  bulkActions?: (context: DataTableBulkContext<TRow>) => ReactNode;

  /** Detail shown in place under a row; adds the expand column. */
  renderExpanded?: (row: TRow) => ReactNode;
  /** Default: every row expands when `renderExpanded` is given. */
  canExpand?: (row: TRow) => boolean;
  /** Rows open at first render. */
  defaultExpandedIds?: readonly string[];

  /** The row click target: a click anywhere on the row, or Enter on it. */
  onRowClick?: (row: TRow) => void;
  /** The kebab at the row's end; the same list opens on right-click. */
  rowActions?: (row: TRow) => readonly DataTableRowAction[];
  getRowTone?: (row: TRow) => DataTableRowTone;

  /** Skeleton rows instead of the body. */
  loading?: boolean;
  /**
   * Skeleton rows while loading: default the page size with pagination,
   * else 5; at most 10 either way.
   */
  loadingRows?: number;
  /** Shown above the table; rows already loaded stay. */
  error?: DataTableError | null;
  /** True while a search or filter narrows the rows: no rows means no results. */
  filtered?: boolean;

  toolbar?: ReactNode;
  /** The empty state (no rows and nothing filtered). */
  empty?: ReactNode;
  /** The no-results state (no rows while `filtered`). */
  noResults?: ReactNode;
  /** Above the pagination, at the table's foot. */
  footer?: ReactNode;

  /**
   * `page` (default): the page scrolls and the header sticks to it.
   * `container`: the table scrolls inside its own box (give it a height with
   * `className`), and long lists render only the rows in view.
   */
  scroll?: "page" | "container";
  className?: string;
}>;
