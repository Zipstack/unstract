import { useVirtualizer } from "@tanstack/react-virtual";
import { InlineAlert } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import {
  containersFrom,
  flattenJson,
  flattenJsonText,
  isTooDeep,
  type JsonLine,
  visibleLines,
} from "@v1/lib/code/json-lines";
import { lineText } from "@v1/lib/code/tokens";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  type ComponentProps,
  type JSX,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  type RefObject,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { CodeBlock } from "./CodeBlock";
import { GUTTER, gutterWidth, MONO, TOOLBAR_BUTTON, Tokens } from "./CodeLines";
import { CopyButton } from "./CopyButton";

/** Above this many showing lines, only the rows in view are rendered. */
export const VIRTUALIZE_ABOVE = 300;
/** A document this long or shorter opens fully expanded; a longer one opens to depth 2. */
export const EXPAND_ALL_UP_TO = 300;
const LARGE_DOCUMENT_DEPTH = 2;
// The mono line height, read from the token at mount; this is its value today.
const FALLBACK_LINE_HEIGHT = 22;
// What the virtualiser assumes before it can measure (and in tests): a
// viewport this tall, so the first paint already shows a screenful of rows.
const INITIAL_VIEWPORT = { width: 0, height: 480 };

export type JsonViewMode = "tree" | "raw";

/**
 * What JsonView shows: a value, or JSON text. Exactly one. Exported apart from
 * the options so a wrapper can `Omit` options without losing the either-or
 * (`Omit` over a union collapses it).
 */
export type JsonSource =
  | Readonly<{ value: unknown; text?: never }>
  | Readonly<{ text: string; value?: never }>;

export type JsonViewOptions = Omit<
  ComponentProps<"div">,
  "children" | "title" | "defaultValue"
> &
  Readonly<{
    /** Controlled mode. */
    mode?: JsonViewMode;
    /** Starting mode when uncontrolled (default `tree`). */
    defaultMode?: JsonViewMode;
    onModeChange?: (mode: JsonViewMode) => void;
    /**
     * Containers at this depth or deeper start collapsed (the root is depth
     * 0). By default a document of up to 300 lines opens fully expanded and a
     * longer one to depth 2.
     */
    defaultExpandDepth?: number;
    showLineNumbers?: boolean;
    /** Shows the Tree / Raw switch (default on). */
    showModeToggle?: boolean;
    title?: ReactNode;
    /** Extra controls in the toolbar, before the copy button. */
    actions?: ReactNode;
    /** Shows a copy button for the pretty-printed JSON (default on). */
    copyable?: boolean;
    /** Names the tree or the raw region (default "JSON"). */
    "aria-label"?: string;
  }>;

export type JsonViewProps = JsonViewOptions & JsonSource;

type Model =
  | Readonly<{ ok: true; lines: JsonLine[] }>
  // `raw` is the text as received; a value that cannot be serialised has none.
  | Readonly<{ ok: false; error: string; title: string; raw?: string }>;

// One shared empty list: a fresh `[]` per render would never equal the last
// one, and the fold reset below would re-render forever.
const NO_LINES: JsonLine[] = [];

function buildModel(source: JsonSource): Model {
  if (source.text !== undefined) {
    try {
      const result = flattenJsonText(source.text);
      return result.ok
        ? result
        : {
            ok: false,
            error: result.error,
            title: "Invalid JSON",
            raw: source.text,
          };
    } catch (error) {
      // Valid JSON nested deeper than the reader and printer can recurse
      // (JSON.parse accepted it) shows as an error, not a crashed page.
      // Anything else is a bug, and is not hidden.
      if (!isTooDeep(error)) {
        throw error;
      }
      return {
        ok: false,
        error: "It is valid, but nested too deeply to show as a tree.",
        title: "This JSON is nested too deeply for the tree",
        raw: source.text,
      };
    }
  }
  try {
    return { ok: true, lines: flattenJson(source.value) };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      title: "This value cannot be shown as JSON",
    };
  }
}

/** A closing line is not a tree item; activating it means activating its container. */
function itemIndex(lines: readonly JsonLine[], index: number): number {
  const line = lines[index];
  return line?.kind === "close" ? (line.openIndex ?? 0) : index;
}

function initialFold(lines: readonly JsonLine[], depth?: number): Set<number> {
  const start =
    depth ??
    (lines.length <= EXPAND_ALL_UP_TO
      ? Number.POSITIVE_INFINITY
      : LARGE_DOCUMENT_DEPTH);
  return containersFrom(lines, start);
}

/**
 * The mono line height from its token, read from the scroll element. `element`
 * names which element is mounted (none while showing an error or "No data",
 * a tree or a raw region), so the token is read again when that changes.
 */
function useLineHeight(
  ref: RefObject<HTMLElement | null>,
  element: string,
): number {
  const [height, setHeight] = useState(FALLBACK_LINE_HEIGHT);
  // biome-ignore lint/correctness/useExhaustiveDependencies: `element` is the trigger; the ref is read inside
  useLayoutEffect(() => {
    if (!ref.current) {
      return;
    }
    const token = Number.parseFloat(
      getComputedStyle(ref.current).getPropertyValue("--type-mono-line-height"),
    );
    if (token > 0) {
      setHeight(token);
    }
  }, [ref, element]);
  return height;
}

/** The last showing row at or before `index` in the full document: itself, or the folded container hiding it. */
function showingPosition(rows: readonly JsonLine[], index: number): number {
  let lo = 0;
  let hi = rows.length - 1;
  let found = 0;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].index <= index) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

const SCROLL_AREA = cn(
  "ui:min-h-0 ui:flex-1 ui:overflow-auto ui:py-2 ui:focus-visible:focus-ring",
  MONO,
);

/**
 * JSON as an expandable tree or as raw pretty-printed text, over one line
 * model. Large documents render only the rows in view, so 5,000 lines stay
 * responsive. Pass `value` (any JSON-serialisable value) or `text` (JSON
 * source, printed as written: numbers are never rounded; invalid text shows
 * an error with the text as it came).
 *
 * Tree keys: Up/Down move, Home/End jump, Right expands (or enters), Left
 * collapses (or goes to the parent), Enter or Space toggles.
 *
 * `value` is compared by identity: a new object re-flattens and resets
 * folding and the keyboard position, so pass a stable (memoised) value.
 *
 * The view grows to 480px and then scrolls; set a height class to change
 * that (`className="ui:h-full ui:max-h-none"`).
 */
export function JsonView({
  value,
  text,
  mode,
  defaultMode = "tree",
  onModeChange,
  defaultExpandDepth,
  showLineNumbers = true,
  showModeToggle = true,
  title,
  actions,
  copyable = true,
  "aria-label": ariaLabel = "JSON",
  className,
  ...props
}: JsonViewProps): JSX.Element {
  const model = useMemo(
    () => buildModel(text === undefined ? { value } : { text }),
    [value, text],
  );
  const lines = model.ok ? model.lines : NO_LINES;

  const [ownMode, setOwnMode] = useState(defaultMode);
  const currentMode = mode ?? ownMode;
  const setMode = (next: JsonViewMode) => {
    if (mode === undefined) {
      setOwnMode(next);
    }
    onModeChange?.(next);
  };

  // Folded containers and the active row, both reset when the document changes.
  const [view, setView] = useState(() => ({
    lines,
    collapsed: initialFold(lines, defaultExpandDepth),
    active: 0,
  }));
  let { collapsed, active } = view;
  if (view.lines !== lines) {
    collapsed = initialFold(lines, defaultExpandDepth);
    active = 0;
    setView({ lines, collapsed, active });
  }
  const setCollapsed = (next: Set<number>) =>
    setView({ lines, collapsed: next, active });
  const setActive = (index: number) =>
    setView({ lines, collapsed, active: itemIndex(lines, index) });

  const tree = currentMode === "tree";
  const rows = useMemo(
    () => (tree ? visibleLines(lines, collapsed) : lines),
    [tree, lines, collapsed],
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const lineHeight = useLineHeight(
    scrollRef,
    !model.ok || lines.length === 0 ? "none" : currentMode,
  );
  const virtual = rows.length > VIRTUALIZE_ABOVE;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => lineHeight,
    overscan: 20,
    enabled: virtual,
    initialRect: INITIAL_VIEWPORT,
  });
  // Rows are placed from estimateSize, which the virtualiser caches: a new
  // line height must re-measure, or rows keep the old spacing.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `lineHeight` is the trigger; estimateSize reads it
  useLayoutEffect(() => {
    virtualizer.measure();
  }, [lineHeight, virtualizer]);

  // A new document starts at the top, where its active row (the root) is:
  // otherwise a scrolled view keeps its offset and the active row is off screen.
  const shownLines = useRef(lines);
  useLayoutEffect(() => {
    if (shownLines.current === lines) {
      return;
    }
    shownLines.current = lines;
    // The scroll event this fires moves a virtualised window too.
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [lines]);

  const [focused, setFocused] = useState(false);
  const activePos = rows.length === 0 ? -1 : showingPosition(rows, active);
  const id = useId();
  const rowId = (line: JsonLine) => `${id}-line-${line.index}`;

  const toggle = (line: JsonLine) => {
    const next = new Set(collapsed);
    if (next.has(line.index)) {
      next.delete(line.index);
    } else {
      next.add(line.index);
    }
    setView({ lines, collapsed: next, active: line.index });
  };

  const scrollTo = (pos: number) => {
    if (virtual) {
      virtualizer.scrollToIndex(pos, { align: "auto" });
    } else {
      scrollRef.current
        ?.querySelector(`[data-pos="${pos}"]`)
        ?.scrollIntoView?.({ block: "nearest" });
    }
  };

  const moveTo = (pos: number) => {
    if (pos < 0 || pos >= rows.length) {
      return;
    }
    setActive(rows[pos].index);
    scrollTo(pos);
  };

  // Steps from `pos` in `step` direction to the next row that is not a closing bracket.
  const step = (pos: number, dir: 1 | -1): number => {
    for (let p = pos + dir; p >= 0 && p < rows.length; p += dir) {
      if (rows[p].kind !== "close") {
        return p;
      }
    }
    return -1;
  };

  // Clicks are handled once, on the tree (rows are not separately
  // interactive; the keyboard handler is here too): a row becomes active, and
  // a click on a container's chevron folds or unfolds it.
  const onTreeClick = (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const pos = Number(
      target.closest("[data-pos]")?.getAttribute("data-pos") ?? Number.NaN,
    );
    const line = rows[pos];
    if (!line) {
      return;
    }
    setActive(line.index);
    scrollRef.current?.focus({ preventScroll: true });
    if (line.kind === "open" && target.closest("[data-slot=json-toggle]")) {
      toggle(line);
    }
  };

  const onTreeKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (activePos < 0) {
      return;
    }
    const line = rows[activePos];
    const isOpen = line.kind === "open";
    const folded = isOpen && collapsed.has(line.index);
    let handled = true;
    switch (event.key) {
      case "ArrowDown":
        moveTo(step(activePos, 1));
        break;
      case "ArrowUp":
        moveTo(step(activePos, -1));
        break;
      case "Home":
        moveTo(0);
        break;
      case "End":
        moveTo(step(rows.length, -1));
        break;
      case "ArrowRight":
        if (folded) {
          toggle(line);
        } else if (isOpen) {
          moveTo(step(activePos, 1));
        }
        break;
      case "ArrowLeft":
        if (isOpen && !folded) {
          toggle(line);
        } else {
          for (let p = activePos - 1; p >= 0; p--) {
            if (rows[p].kind === "open" && rows[p].depth === line.depth - 1) {
              moveTo(p);
              break;
            }
          }
        }
        break;
      case "Enter":
      case " ":
        if (isOpen) {
          toggle(line);
        }
        break;
      default:
        handled = false;
    }
    if (handled) {
      event.preventDefault();
    }
  };

  const items = virtual
    ? virtualizer.getVirtualItems()
    : rows.map((_, index) => ({ index, start: 0 }));
  const activeRendered =
    activePos >= 0 && items.some((item) => item.index === activePos);

  const renderRow = (pos: number, start: number) => {
    const line = rows[pos];
    const folded = tree && line.kind === "open" && collapsed.has(line.index);
    const isActive = tree && focused && pos === activePos;
    const treeAttrs =
      tree && line.kind !== "close"
        ? {
            role: "treeitem",
            id: rowId(line),
            "aria-level": line.depth + 1,
            "aria-expanded":
              line.kind === "open" ? !collapsed.has(line.index) : undefined,
          }
        : tree
          ? { "aria-hidden": true }
          : {};
    return (
      <div
        key={line.index}
        data-slot="json-line"
        data-pos={pos}
        data-active={isActive || undefined}
        {...treeAttrs}
        style={{ "--json-row-y": virtual ? `${start}px` : undefined }}
        className={cn(
          "ui:flex ui:min-h-lh ui:whitespace-pre ui:px-3",
          virtual &&
            "ui:absolute ui:inset-x-0 ui:top-0 ui:translate-y-(--json-row-y)",
          isActive && "ui:bg-accent",
        )}
      >
        {showLineNumbers ? (
          <span aria-hidden className={GUTTER}>
            {line.index + 1}
          </span>
        ) : null}
        {tree ? (
          <span
            aria-hidden
            data-slot={line.kind === "open" ? "json-toggle" : undefined}
            className={cn(
              "ui:inline-flex ui:w-4 ui:shrink-0 ui:items-center ui:justify-center ui:text-muted-foreground",
              line.kind === "open" &&
                "ui:cursor-pointer ui:hover:text-foreground",
            )}
          >
            {line.kind !== "open" ? null : folded ? (
              <ChevronRight className="ui:size-3.5" />
            ) : (
              <ChevronDown className="ui:size-3.5" />
            )}
          </span>
        ) : null}
        <span>
          <Tokens line={line.tokens} />
          {folded ? (
            <>
              <span className="ui:text-muted-foreground">…</span>
              <Tokens line={line.closeTokens ?? []} />
              <span className="ui:pl-2 ui:font-sans ui:text-caption ui:text-muted-foreground">
                {line.summary}
              </span>
            </>
          ) : null}
        </span>
      </div>
    );
  };

  const body = virtual ? (
    <div
      role="none"
      className="ui:relative ui:h-(--json-total)"
      style={{ "--json-total": `${virtualizer.getTotalSize()}px` }}
    >
      {items.map((item) => renderRow(item.index, item.start))}
    </div>
  ) : (
    items.map((item) => renderRow(item.index, item.start))
  );

  const toolbar =
    title != null || actions != null || copyable || showModeToggle;

  return (
    <div
      data-slot="json-view"
      data-mode={currentMode}
      data-state={model.ok ? "valid" : "invalid"}
      className={cn(
        "ui:flex ui:max-h-120 ui:min-h-0 ui:flex-col ui:overflow-hidden ui:rounded-lg ui:border ui:border-border ui:bg-muted ui:text-foreground",
        className,
      )}
      {...props}
    >
      {toolbar ? (
        <div
          data-slot="json-view-toolbar"
          className="ui:flex ui:items-center ui:gap-1 ui:border-b ui:border-border ui:py-1 ui:pr-1 ui:pl-3"
        >
          <div className="ui:min-w-0 ui:flex-1 ui:truncate ui:text-caption ui:font-medium ui:text-muted-foreground">
            {title}
          </div>
          {model.ok && showModeToggle ? (
            // biome-ignore lint/a11y/useSemanticElements: a fieldset needs a legend and adds a border; a labelled group of toggle buttons is the documented pattern.
            <div role="group" aria-label="View" className="ui:flex">
              {(["tree", "raw"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={currentMode === m}
                  onClick={() => setMode(m)}
                  className={cn(
                    TOOLBAR_BUTTON,
                    currentMode === m && "ui:bg-card ui:text-foreground",
                  )}
                >
                  {m === "tree" ? "Tree" : "Raw"}
                </button>
              ))}
            </div>
          ) : null}
          {model.ok && tree && lines.length > 0 ? (
            <>
              <button
                type="button"
                className={TOOLBAR_BUTTON}
                onClick={() => setCollapsed(new Set())}
              >
                Expand all
              </button>
              <button
                type="button"
                className={TOOLBAR_BUTTON}
                onClick={() => setCollapsed(containersFrom(lines, 1))}
              >
                Collapse all
              </button>
            </>
          ) : null}
          {actions}
          {copyable && (model.ok || model.raw !== undefined) ? (
            <CopyButton
              label="Copy JSON"
              text={() =>
                model.ok
                  ? lines.map((line) => lineText(line.tokens)).join("\n")
                  : (model.raw ?? "")
              }
            />
          ) : null}
        </div>
      ) : null}
      {model.ok ? (
        lines.length === 0 ? (
          <p className="ui:m-0 ui:p-3 ui:text-body-small ui:text-muted-foreground">
            No data
          </p>
        ) : tree ? (
          <div
            ref={scrollRef}
            role="tree"
            aria-label={ariaLabel}
            aria-activedescendant={
              activeRendered ? rowId(rows[activePos]) : undefined
            }
            tabIndex={0}
            onKeyDown={onTreeKeyDown}
            onClick={onTreeClick}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            style={{ "--code-gutter": gutterWidth(lines.length) }}
            className={SCROLL_AREA}
          >
            {body}
          </div>
        ) : (
          <section
            ref={scrollRef}
            aria-label={ariaLabel}
            // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable (WCAG 2.1.1)
            tabIndex={0} // NOSONAR: a scrollable region must be focusable (WCAG 2.1.1)
            style={{ "--code-gutter": gutterWidth(lines.length) }}
            className={SCROLL_AREA}
          >
            {body}
          </section>
        )
      ) : (
        <div className="ui:flex ui:min-h-0 ui:flex-col ui:gap-2 ui:p-2">
          <InlineAlert title={model.title}>{model.error}</InlineAlert>
          {model.raw === undefined ? null : (
            <CodeBlock
              code={model.raw}
              copyable={false}
              showLineNumbers
              aria-label={`${ariaLabel} (as received)`}
              className="ui:min-h-0 ui:bg-card"
            />
          )}
        </div>
      )}
    </div>
  );
}
