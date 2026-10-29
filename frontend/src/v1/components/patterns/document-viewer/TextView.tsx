import { cn } from "@v1/lib/cn";
import type { HighlightTone } from "@v1/lib/pdf/highlights";
import {
  type KeyboardEvent,
  type Ref,
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

const NO_HIGHLIGHTS: readonly TextLineHighlight[] = [];

const TONES: Record<HighlightTone, string> = {
  default: "ui:bg-primary/15",
  active: "ui:bg-primary/30 ui:ring-1 ui:ring-primary",
  "low-confidence": "ui:bg-destructive/15",
};

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
        root.scrollTop =
          line.offsetTop + line.offsetHeight / 2 - root.clientHeight / 2;
        return true;
      },
    }),
    [highlights],
  );

  if (text.trim() === "") {
    return (
      <ViewerStatus
        state={{ status: "empty" }}
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
      <ol className="ui:m-0 ui:list-none ui:p-0 ui:text-mono ui:font-mono ui:text-card-foreground">
        {lines.map((content, index) => {
          const highlight = byLine.get(index);
          const tone: HighlightTone | null = highlight
            ? highlight.id === activeHighlightId
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
              // Lines never reorder; the index is the line number.
              // biome-ignore lint/suspicious/noArrayIndexKey: the index is the line's identity
              key={index}
              data-line={index}
              data-tone={tone ?? undefined}
              data-highlight-id={highlight?.id}
              className={cn(
                "ui:grid ui:grid-cols-[auto_1fr] ui:gap-3 ui:px-3",
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
        })}
      </ol>
    </section>
  );
}
