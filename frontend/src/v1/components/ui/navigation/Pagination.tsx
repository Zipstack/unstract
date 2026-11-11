import { cn } from "@v1/lib/cn";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { type JSX, type KeyboardEvent, useId, useState } from "react";

export const DEFAULT_PAGE_SIZES: readonly number[] = [10, 20, 50, 100];

export type PaginationProps = Readonly<{
  /** The current page, from 1. */
  page: number;
  pageSize: number;
  /** Entries across all pages. */
  total: number;
  onPageChange: (page: number) => void;
  /** Shows the page-size select when given. */
  onPageSizeChange?: (pageSize: number) => void;
  pageSizeOptions?: readonly number[];
  /** Names the landmark; default "Pagination". */
  "aria-label"?: string;
  className?: string;
}>;

/** Pages needed for `total` entries; at least 1, so an empty list is page 1 of 1. */
export function pageCount(total: number, pageSize: number): number {
  if (!(pageSize > 0) || !(total > 0)) {
    return 1;
  }
  return Math.ceil(total / pageSize);
}

/** "Showing 1 to 10 of 42 entries", the table-footer copy of frame 756:982. */
export function rangeText(
  page: number,
  pageSize: number,
  total: number,
): string {
  if (!(total > 0)) {
    return "No entries";
  }
  const first = Math.min((page - 1) * pageSize + 1, total);
  const last = Math.min(page * pageSize, total);
  return `Showing ${first} to ${last} of ${total} ${total === 1 ? "entry" : "entries"}`;
}

const CONTROL =
  "ui:box-border ui:inline-flex ui:h-8 ui:items-center ui:justify-center ui:gap-1 ui:rounded-md ui:border ui:border-solid ui:border-border ui:bg-card ui:font-sans ui:text-body-small ui:font-medium ui:text-foreground ui:outline-none ui:focus-visible:focus-ring";

const BUTTON = cn(
  CONTROL,
  "ui:cursor-pointer ui:px-3 ui:not-disabled:hover:bg-accent ui:disabled:cursor-not-allowed ui:disabled:text-muted-foreground ui:disabled:opacity-60",
);

/**
 * Range text, page size, Previous and Next, and a page box that jumps on
 * Enter (Escape or leaving the box puts the current page back). Previous is
 * disabled on the first page and Next on the last.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = DEFAULT_PAGE_SIZES,
  "aria-label": label = "Pagination",
  className,
}: PaginationProps): JSX.Element {
  const pages = pageCount(total, pageSize);
  const current = Math.min(Math.max(1, Math.trunc(page) || 1), pages);
  const [draft, setDraft] = useState<string | null>(null);
  const sizeId = useId();

  const go = (target: number): void => {
    const next = Math.min(Math.max(1, target), pages);
    if (next !== current) {
      onPageChange(next);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      const typed = Number.parseInt(draft ?? "", 10);
      setDraft(null);
      if (Number.isFinite(typed)) {
        go(typed);
      }
    } else if (event.key === "Escape") {
      setDraft(null);
    }
  };

  return (
    <nav
      data-slot="pagination"
      aria-label={label}
      className={cn(
        "ui:flex ui:flex-wrap ui:items-center ui:gap-2 ui:text-body-small ui:text-muted-foreground",
        className,
      )}
    >
      <p className="ui:m-0" aria-live="polite">
        {rangeText(current, pageSize, total)}
      </p>
      <span className="ui:flex-1" />
      {onPageSizeChange && (
        <span className="ui:inline-flex ui:items-center ui:gap-2">
          <label htmlFor={sizeId}>Rows per page</label>
          <select
            id={sizeId}
            value={pageSize}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
            className={cn(CONTROL, "ui:cursor-pointer ui:px-2")}
          >
            {(pageSizeOptions.includes(pageSize)
              ? pageSizeOptions
              : [...pageSizeOptions, pageSize].sort((a, b) => a - b)
            ).map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </span>
      )}
      <span className="ui:inline-flex ui:items-center ui:gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={current <= 1}
          onClick={() => go(current - 1)}
        >
          <ChevronLeft aria-hidden className="ui:size-3.5" />
          Previous
        </button>
        <span className="ui:inline-flex ui:items-center ui:gap-2">
          <span aria-hidden>Page</span>
          <input
            type="text"
            inputMode="numeric"
            aria-label={`Page number, 1 to ${pages}`}
            value={draft ?? String(current)}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onKeyDown}
            onBlur={() => setDraft(null)}
            disabled={pages <= 1}
            className={cn(
              CONTROL,
              "ui:w-12 ui:px-2 ui:text-center ui:disabled:text-muted-foreground",
            )}
          />
          <span aria-hidden>{`of ${pages}`}</span>
        </span>
        <button
          type="button"
          className={BUTTON}
          disabled={current >= pages}
          onClick={() => go(current + 1)}
        >
          Next
          <ChevronRight aria-hidden className="ui:size-3.5" />
        </button>
      </span>
    </nav>
  );
}
