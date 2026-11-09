import { InlineAlert } from "@v1/components/ui/feedback";
import { cn } from "@v1/lib/cn";
import {
  computeLineDiff,
  type DiffRowKind,
  type DiffStats,
  describeChanges,
  type LineDiff,
} from "@v1/lib/code/diff";
import { type CodeLanguage, highlightLines } from "@v1/lib/code/highlight";
import { type CodeLine, plural } from "@v1/lib/code/tokens";
import { type ComponentProps, type JSX, type ReactNode, useMemo } from "react";
import { GUTTER, gutterWidth, MONO, Tokens } from "./CodeLines";

export type DiffLayout = "split" | "unified";

// What renders while a diff is past its limits: nothing to show.
const NO_DIFF: LineDiff = {
  oldLines: [],
  newLines: [],
  unified: [],
  split: [],
  stats: { changes: 0, added: 0, removed: 0, endingsOnly: false },
};

export type DiffViewProps = Omit<ComponentProps<"div">, "children"> &
  Readonly<{
    /**
     * The text before the change. For JSON text, pass `formatJsonText(text)`
     * (numbers kept as written); for a value, `formatJson(value)`.
     */
    oldText: string;
    /** The text after the change. */
    newText: string;
    /** Highlighting grammar for both sides (default `text`). */
    language?: CodeLanguage;
    /** `split` (side by side, the default) or `unified` (one column). */
    layout?: DiffLayout;
    /** Heads the old side in the split layout ("v1 - Auto-generated", "BEFORE"). */
    oldLabel?: ReactNode;
    /** Heads the new side in the split layout. */
    newLabel?: ReactNode;
    /** Shows the "1 change +2 −1" bar (default on). */
    showSummary?: boolean;
    showLineNumbers?: boolean;
    /** Wraps long lines (default on, so no change hides off the side). */
    wrap?: boolean;
    /** Names the scrollable diff region (default "Changes"). */
    "aria-label"?: string;
  }>;

const ROW_TONE: Readonly<Record<DiffRowKind, string>> = {
  context: "",
  added: "ui:bg-diff-added",
  removed: "ui:bg-diff-removed",
};
const SIGN: Readonly<Record<DiffRowKind, string>> = {
  context: " ",
  added: "+",
  removed: "−",
};
const SIGN_TONE: Readonly<Record<DiffRowKind, string>> = {
  context: "",
  added: "ui:text-diff-added-foreground",
  removed: "ui:text-diff-removed-foreground",
};
// Read before a changed line, so the change is not carried by colour alone.
const SPOKEN: Readonly<Record<DiffRowKind, string>> = {
  context: "",
  added: "Added: ",
  removed: "Removed: ",
};

export type DiffSummaryProps = Readonly<{
  /** From `diffStats(oldText, newText)`. */
  stats: DiffStats;
  className?: string;
}>;

/** The "1 change +2 −1" summary; also usable on its own. */
export function DiffSummary({
  stats,
  className,
}: DiffSummaryProps): JSX.Element {
  return (
    <p
      data-slot="diff-summary"
      className={cn(
        "ui:m-0 ui:flex ui:items-center ui:gap-2.5 ui:text-caption ui:font-medium ui:text-foreground",
        className,
      )}
    >
      <span>{describeChanges(stats)}</span>
      {stats.changes > 0 ? (
        <>
          <span className={cn(MONO, "ui:text-diff-added-foreground")}>
            <span aria-hidden>+{stats.added}</span>
            <span className="ui:sr-only">
              {plural(stats.added, "line")} added
            </span>
          </span>
          <span className={cn(MONO, "ui:text-diff-removed-foreground")}>
            <span aria-hidden>−{stats.removed}</span>
            <span className="ui:sr-only">
              {plural(stats.removed, "line")} removed
            </span>
          </span>
        </>
      ) : null}
    </p>
  );
}

type CellProps = Readonly<{
  kind?: DiffRowKind;
  number?: number;
  line?: CodeLine;
  showLineNumbers: boolean;
  wrap: boolean;
  className?: string;
}>;

function Cell({
  kind,
  number,
  line,
  showLineNumbers,
  wrap,
  className,
}: CellProps): JSX.Element {
  return (
    <div
      data-slot="diff-cell"
      data-kind={kind ?? "empty"}
      className={cn(
        "ui:flex ui:min-h-lh ui:min-w-0 ui:pl-3",
        kind ? ROW_TONE[kind] : "ui:bg-muted",
        className,
      )}
    >
      {showLineNumbers ? (
        <span aria-hidden className={GUTTER}>
          {number}
        </span>
      ) : null}
      <span
        aria-hidden
        className={cn(
          "ui:w-4 ui:shrink-0 ui:select-none",
          kind && SIGN_TONE[kind],
        )}
      >
        {kind ? SIGN[kind] : ""}
      </span>
      <span
        className={cn(
          "ui:min-w-0 ui:flex-1 ui:pr-3",
          wrap ? "ui:whitespace-pre-wrap ui:break-all" : "ui:whitespace-pre",
        )}
      >
        {kind && SPOKEN[kind] ? (
          <span className="ui:sr-only">{SPOKEN[kind]}</span>
        ) : null}
        {line ? <Tokens line={line} /> : null}
      </span>
    </div>
  );
}

/**
 * What changed between two texts, line by line: side by side (frame V12) or
 * unified. Changed lines are tinted with the diff tokens, marked + / −, and
 * prefixed for screen readers.
 */
export function DiffView({
  oldText,
  newText,
  language = "text",
  layout = "split",
  oldLabel,
  newLabel,
  showSummary = true,
  showLineNumbers = true,
  wrap = true,
  "aria-label": ariaLabel = "Changes",
  className,
  ...props
}: DiffViewProps): JSX.Element {
  const computed = useMemo(
    () => computeLineDiff(oldText, newText),
    [oldText, newText],
  );
  const diff = computed ?? NO_DIFF;
  const oldTokens = useMemo(
    () => highlightLines(diff.oldLines.join("\n"), language),
    [diff.oldLines, language],
  );
  const newTokens = useMemo(
    () => highlightLines(diff.newLines.join("\n"), language),
    [diff.newLines, language],
  );
  const cell = { showLineNumbers, wrap };
  const labels = layout === "split" && (oldLabel != null || newLabel != null);

  return (
    <div
      data-slot="diff-view"
      data-layout={layout}
      className={cn(
        "ui:flex ui:min-h-0 ui:flex-col ui:overflow-hidden ui:rounded-lg ui:border ui:border-border ui:bg-card ui:text-foreground",
        className,
      )}
      {...props}
    >
      {computed === null ? (
        <InlineAlert
          kind="warning"
          title="Too large to compare"
          className="ui:m-2"
        >
          These texts are too long, or differ in too many lines, to compare line
          by line here.
        </InlineAlert>
      ) : null}
      {showSummary && computed !== null ? (
        <DiffSummary
          stats={diff.stats}
          className="ui:border-b ui:border-border ui:bg-muted ui:px-3.5 ui:py-2"
        />
      ) : null}
      {labels && computed !== null ? (
        <div
          data-slot="diff-labels"
          className="ui:grid ui:grid-cols-2 ui:border-b ui:border-border ui:text-overline ui:text-muted-foreground"
        >
          <div className="ui:px-3 ui:py-1.5">{oldLabel}</div>
          <div className="ui:border-l ui:border-border ui:px-3 ui:py-1.5">
            {newLabel}
          </div>
        </div>
      ) : null}
      {computed === null ? null : (
        <section
          aria-label={ariaLabel}
          // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable (WCAG 2.1.1)
          tabIndex={0} // NOSONAR: a scrollable region must be focusable (WCAG 2.1.1)
          style={{
            "--code-gutter": gutterWidth(
              Math.max(diff.oldLines.length, diff.newLines.length),
            ),
          }}
          className={cn(
            "ui:min-h-0 ui:flex-1 ui:overflow-auto ui:py-2 ui:focus-visible:focus-ring",
            MONO,
          )}
        >
          {layout === "split"
            ? diff.split.map((row, i) => (
                <div
                  // biome-ignore lint/suspicious/noArrayIndexKey: a row is identified by its position.
                  key={i}
                  data-slot="diff-row"
                  className="ui:grid ui:grid-cols-2"
                >
                  <Cell
                    {...cell}
                    kind={row.old?.kind}
                    number={row.old ? row.old.line + 1 : undefined}
                    line={row.old ? oldTokens[row.old.line] : undefined}
                  />
                  <Cell
                    {...cell}
                    kind={row.new?.kind}
                    number={row.new ? row.new.line + 1 : undefined}
                    line={row.new ? newTokens[row.new.line] : undefined}
                    className="ui:border-l ui:border-border"
                  />
                </div>
              ))
            : diff.unified.map((row, i) => (
                <div
                  // biome-ignore lint/suspicious/noArrayIndexKey: a row is identified by its position.
                  key={i}
                  data-slot="diff-row"
                  data-kind={row.kind}
                  className={cn("ui:flex", ROW_TONE[row.kind])}
                >
                  {showLineNumbers ? (
                    <span aria-hidden className={cn(GUTTER, "ui:pl-3")}>
                      {row.oldLine === undefined ? "" : row.oldLine + 1}
                    </span>
                  ) : null}
                  <Cell
                    {...cell}
                    kind={row.kind}
                    number={
                      row.newLine === undefined ? undefined : row.newLine + 1
                    }
                    line={
                      row.kind === "removed"
                        ? oldTokens[row.oldLine as number]
                        : newTokens[row.newLine as number]
                    }
                    className="ui:flex-1 ui:bg-transparent ui:pl-0"
                  />
                </div>
              ))}
        </section>
      )}
    </div>
  );
}
