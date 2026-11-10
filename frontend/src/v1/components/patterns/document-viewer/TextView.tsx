import { cn } from "@v1/lib/cn";
import { type HighlightTone, NO_HIGHLIGHTS } from "@v1/lib/pdf/highlights";
import {
  type KeyboardEvent,
  memo,
  type Ref,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
} from "react";
import type { PdfPageListHandle } from "./PdfPageList";
import { ViewerStatus } from "./ViewerStatus";

/** A highlighted line of text. Lines are 0-based, as LLMWhisperer numbers them. */
export interface TextLineHighlight {
  id: string;
  line: number;
  tone?: HighlightTone;
}

export interface TextViewProps {
  text: string;
  highlights?: readonly TextLineHighlight[];
  activeHighlightId?: string | null;
  onHighlightClick?: (highlight: TextLineHighlight) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
  ref?: Ref<PdfPageListHandle>;
}

const TONES: Record<HighlightTone, string> = {
  default: "ui:bg-primary/15",
  active: "ui:bg-primary/30 ui:ring-1 ui:ring-primary",
  "low-confidence": "ui:bg-destructive/15",
};

/**
 * One line. Memoised so that moving the active highlight re-renders only the
 * lines it leaves and reaches, not every line of a long result.
 */
const TextLine = memo(function TextLine({
  index,
  content,
  highlight,
  active,
  onHighlightClick,
}: {
  index: number;
  content: string;
  highlight: TextLineHighlight | undefined;
  active: boolean;
  onHighlightClick?: (highlight: TextLineHighlight) => void;
}) {
  const tone: HighlightTone | null = highlight
    ? active
      ? "active"
      : (highlight.tone ?? "default")
    : null;
  const body =
    highlight && onHighlightClick ? (
      <button
        type="button"
        onClick={() => onHighlightClick(highlight)}
        aria-current={tone === "active" ? "true" : undefined}
        className="ui:block ui:w-full ui:cursor-pointer ui:text-left ui:whitespace-pre-wrap ui:focus-visible:focus-ring"
      >
        {content || " "}
      </button>
    ) : (
      <span className="ui:whitespace-pre-wrap">{content || " "}</span>
    );
  return (
    <li
      data-line={index}
      data-tone={tone ?? undefined}
      data-highlight-id={highlight?.id}
      className={cn(
        // Every line stays in the DOM, so find in page, copy and scrolling to a
        // line keep working, but the browser skips layout and paint for lines
        // off screen; it remembers a line's height once it has drawn it.
        "ui:grid ui:grid-cols-[var(--gutter)_1fr] ui:gap-3 ui:px-3 ui:[content-visibility:auto] ui:[contain-intrinsic-size:auto_1lh]",
        tone && TONES[tone],
      )}
    >
      <span
        aria-hidden="true"
        className="ui:select-none ui:text-right ui:text-muted-foreground"
      >
        {index + 1}
      </span>
      {body}
    </li>
  );
});

/**
 * Text shown line by line with line numbers, as extracted (Raw Text, HITL
 * text, an LLMWhisperer result), with whole lines highlighted.
 */
export function TextView({
  text,
  highlights = NO_HIGHLIGHTS,
  activeHighlightId,
  onHighlightClick,
  onKeyDown,
  ref,
}: TextViewProps) {
  const rootRef = useRef<HTMLElement | null>(null);
  // The frame that re-centres a highlight once its rows have been drawn.
  const recentreRef = useRef(0);
  useEffect(() => () => cancelAnimationFrame(recentreRef.current), []);
  const lines = useMemo(() => text.split(/\r\n|\r|\n/), [text]);
  // The last highlight on a line decides how it looks.
  const byLine = useMemo(() => {
    const map = new Map<number, TextLineHighlight>();
    for (const highlight of highlights) {
      map.set(highlight.line, highlight);
    }
    return map;
  }, [highlights]);

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage() {
        // The latest request wins over a highlight still being centred.
        cancelAnimationFrame(recentreRef.current);
        if (rootRef.current) {
          rootRef.current.scrollTop = 0;
        }
      },
      scrollToHighlight(id) {
        const highlight = highlights.find((candidate) => candidate.id === id);
        const root = rootRef.current;
        const line =
          highlight &&
          root?.querySelector<HTMLElement>(`[data-line="${highlight.line}"]`);
        if (!root || !line) {
          return false;
        }
        // Lines the browser has not drawn yet count as one line high, so the
        // first jump can land short of a wrapped line. Centre again once the
        // rows in view are drawn, until the line stays put.
        const centre = () =>
          line.offsetTop + line.offsetHeight / 2 - root.clientHeight / 2;
        cancelAnimationFrame(recentreRef.current);
        root.scrollTop = centre();
        let passes = 3;
        const recentre = () => {
          const target = centre();
          if (Math.abs(root.scrollTop - target) < 1 || --passes === 0) {
            return;
          }
          root.scrollTop = target;
          recentreRef.current = requestAnimationFrame(recentre);
        };
        recentreRef.current = requestAnimationFrame(recentre);
        return true;
      },
    }),
    [highlights],
  );

  if (text.trim() === "") {
    return (
      <ViewerStatus
        state={{ status: "no-text" }}
        onRetry={() => undefined}
        onSubmitPassword={() => undefined}
      />
    );
  }

  return (
    // biome-ignore lint/a11y/noNoninteractiveElementInteractions: the keys belong to the focusable scroll region
    <section
      ref={rootRef}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrollable region must be focusable
      tabIndex={0}
      aria-label="Document text"
      onKeyDown={onKeyDown}
      className="ui:relative ui:h-full ui:overflow-auto ui:bg-card ui:py-2 ui:focus-visible:focus-ring"
    >
      <ol
        className="ui:m-0 ui:list-none ui:p-0 ui:text-mono ui:font-mono ui:text-card-foreground"
        // One gutter for every row, as wide as the longest line number, so the
        // text keeps its columns when the numbers gain a digit.
        style={{ "--gutter": `${String(lines.length).length}ch` }}
      >
        {lines.map((content, index) => {
          const highlight = byLine.get(index);
          return (
            <TextLine
              // Lines never reorder; the index is the line number.
              // biome-ignore lint/suspicious/noArrayIndexKey: the index is the line's identity
              key={index}
              index={index}
              content={content}
              highlight={highlight}
              active={
                highlight !== undefined && highlight.id === activeHighlightId
              }
              onHighlightClick={onHighlightClick}
            />
          );
        })}
      </ol>
    </section>
  );
}
