import { cn } from "@v1/lib/cn";
import { formatZoom, type ZoomMode } from "@v1/lib/pdf/zoom";
import {
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
  MoveHorizontal,
  Scan,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { type FormEvent, type ReactNode, useId, useState } from "react";

export interface ViewerToolbarProps {
  /** 0-based. */
  pageIndex: number;
  pageCount: number;
  zoom: number;
  zoomMode: ZoomMode;
  canZoomIn: boolean;
  canZoomOut: boolean;
  onPageChange: (index: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitWidth: () => void;
  onFitPage: () => void;
  /** Leading content, such as a document switcher (Figma C10). */
  leading?: ReactNode;
  /** Paging controls; off for a single image. */
  showPaging?: boolean;
  /** Zoom and fit controls; off for text. */
  showZoom?: boolean;
  className?: string;
}

const iconButton =
  "ui:inline-flex ui:size-8 ui:shrink-0 ui:items-center ui:justify-center ui:rounded-md ui:text-foreground ui:hover:bg-accent ui:disabled:pointer-events-none ui:disabled:opacity-50 ui:aria-pressed:bg-accent ui:focus-visible:focus-ring";

function ToolbarButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  pressed,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      className={iconButton}
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon aria-hidden="true" className="ui:size-4" />
    </button>
  );
}

/** The page box: shows the current page, and jumps to a typed one on Enter. */
function PageInput({
  pageIndex,
  pageCount,
  onPageChange,
}: Pick<ViewerToolbarProps, "pageIndex" | "pageCount" | "onPageChange">) {
  // What the reader is typing, or null when they are not editing: then the
  // box follows the current page, and a page change never discards a draft.
  const [draft, setDraft] = useState<string | null>(null);
  const id = useId();
  const commit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Whole digits only: parseInt would read "12.7" or "3abc" as a page.
    const typed = (draft ?? "").trim();
    const page = /^\d+$/.test(typed) ? Number(typed) : Number.NaN;
    if (page >= 1 && page <= pageCount) {
      onPageChange(page - 1);
    }
    setDraft(null);
  };
  return (
    <form
      onSubmit={commit}
      className="ui:flex ui:items-center ui:gap-1 ui:text-body-small"
    >
      <label htmlFor={id} className="ui:sr-only">
        Page
      </label>
      <input
        id={id}
        inputMode="numeric"
        autoComplete="off"
        value={draft ?? String(pageIndex + 1)}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => setDraft(null)}
        className="ui:w-10 ui:rounded-md ui:border ui:border-input ui:bg-background ui:px-1 ui:py-1 ui:text-center ui:text-foreground ui:focus-visible:focus-ring"
      />
      <span className="ui:text-muted-foreground">/ {pageCount}</span>
    </form>
  );
}

/** Paging and zoom controls for the document viewer. */
export function ViewerToolbar({
  pageIndex,
  pageCount,
  zoom,
  zoomMode,
  canZoomIn,
  canZoomOut,
  onPageChange,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onFitPage,
  leading,
  showPaging = true,
  showZoom = true,
  className,
}: ViewerToolbarProps) {
  return (
    <div
      role="toolbar"
      aria-label="Document controls"
      className={cn(
        "ui:flex ui:flex-wrap ui:items-center ui:justify-between ui:gap-2 ui:border-b ui:border-border ui:bg-background ui:px-2 ui:py-1",
        className,
      )}
    >
      <div className="ui:flex ui:min-w-0 ui:items-center ui:gap-2">
        {leading}
        {showPaging && (
          <div className="ui:flex ui:items-center ui:gap-1">
            <ToolbarButton
              icon={ChevronLeft}
              label="Previous page"
              disabled={pageIndex <= 0}
              onClick={() => onPageChange(pageIndex - 1)}
            />
            <PageInput
              pageIndex={pageIndex}
              pageCount={pageCount}
              onPageChange={onPageChange}
            />
            <ToolbarButton
              icon={ChevronRight}
              label="Next page"
              disabled={pageIndex >= pageCount - 1}
              onClick={() => onPageChange(pageIndex + 1)}
            />
          </div>
        )}
      </div>
      {showZoom && (
        <div className="ui:flex ui:items-center ui:gap-1">
          <ToolbarButton
            icon={ZoomOut}
            label="Zoom out"
            disabled={!canZoomOut}
            onClick={onZoomOut}
          />
          <output
            aria-live="polite"
            aria-label="Zoom level"
            className="ui:w-12 ui:text-center ui:text-body-small ui:text-muted-foreground"
          >
            {formatZoom(zoom)}
          </output>
          <ToolbarButton
            icon={ZoomIn}
            label="Zoom in"
            disabled={!canZoomIn}
            onClick={onZoomIn}
          />
          <ToolbarButton
            icon={MoveHorizontal}
            label="Fit width"
            pressed={zoomMode === "fit-width"}
            onClick={onFitWidth}
          />
          <ToolbarButton
            icon={Scan}
            label="Fit page"
            pressed={zoomMode === "fit-page"}
            onClick={onFitPage}
          />
        </div>
      )}
    </div>
  );
}
