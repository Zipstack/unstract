import { cn } from "@v1/lib/cn";
import type { Highlight, HighlightTone } from "@v1/lib/pdf/highlights";
import { useCallback } from "react";

export interface HighlightLayerProps {
  /** This page's highlights. */
  highlights: readonly Highlight[];
  /** Shown in the active tone, whatever its own tone. */
  activeId?: string | null;
  /** When given, highlights are buttons that report clicks. */
  onHighlightClick?: (highlight: Highlight) => void;
}

const TONES: Record<HighlightTone, string> = {
  default: "ui:bg-primary/25",
  active: "ui:bg-primary/40 ui:ring-2 ui:ring-primary",
  "low-confidence": "ui:bg-destructive/25",
};

function percent(fraction: number): string {
  return `${fraction * 100}%`;
}

/**
 * Positions a highlight from its page fractions. They are percentages of the
 * page box, so the box needs no update when the zoom changes. Set as custom
 * properties because v1 bans the style attribute.
 */
function usePlacement(highlight: Highlight) {
  const { x, y, w, h } = highlight;
  return useCallback(
    (element: HTMLElement | null) => {
      element?.style.setProperty("--hl-x", percent(x));
      element?.style.setProperty("--hl-y", percent(y));
      element?.style.setProperty("--hl-w", percent(w));
      element?.style.setProperty("--hl-h", percent(h));
    },
    [x, y, w, h],
  );
}

function label(highlight: Highlight, pageNumber: number): string {
  const confidence =
    highlight.confidence === undefined
      ? ""
      : `, ${Math.round(highlight.confidence * 100)}% confidence`;
  return `Highlight on page ${pageNumber}${confidence}`;
}

function HighlightBox({
  highlight,
  active,
  onClick,
}: {
  highlight: Highlight;
  active: boolean;
  onClick?: (highlight: Highlight) => void;
}) {
  const place = usePlacement(highlight);
  const tone: HighlightTone = active ? "active" : highlight.tone;
  const className = cn(
    "ui:absolute ui:top-(--hl-y) ui:left-(--hl-x) ui:h-(--hl-h) ui:w-(--hl-w) ui:rounded-sm ui:mix-blend-multiply",
    TONES[tone],
  );
  const data = {
    "data-highlight-id": highlight.id,
    "data-variant": highlight.variant,
    "data-tone": tone,
  };
  if (onClick === undefined) {
    return <div ref={place} className={className} {...data} />;
  }
  return (
    <button
      ref={place}
      type="button"
      aria-label={label(highlight, highlight.page + 1)}
      aria-current={active ? "true" : undefined}
      onClick={() => onClick(highlight)}
      className={cn(
        className,
        "ui:pointer-events-auto ui:cursor-pointer ui:focus-visible:focus-ring",
      )}
      {...data}
    />
  );
}

/** The highlights of one page, laid over it. Sized by its page, not by itself. */
export function HighlightLayer({
  highlights,
  activeId,
  onHighlightClick,
}: HighlightLayerProps) {
  if (highlights.length === 0) {
    return null;
  }
  return (
    <div className="ui:pointer-events-none ui:absolute ui:inset-0">
      {highlights.map((highlight) => (
        <HighlightBox
          key={highlight.id}
          highlight={highlight}
          active={highlight.id === activeId}
          onClick={onHighlightClick}
        />
      ))}
    </div>
  );
}
