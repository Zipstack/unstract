import { cn } from "@v1/lib/cn";
import type { Highlight, HighlightTone } from "@v1/lib/pdf/highlights";

export interface HighlightLayerProps {
  /** This page's highlights. */
  highlights: readonly Highlight[];
  /** Shown in the active tone, whatever its own tone. */
  activeId?: string | null;
  /** When given, highlights are buttons that report clicks. */
  onHighlightClick?: (highlight: Highlight) => void;
  /**
   * Whether the page's canvas has painted. Until then the boxes sit on the
   * page placeholder, which is dark in dark themes, so they skip the multiply
   * blend (it would hide them) and show as plain translucent fills.
   */
  painted?: boolean;
}

const TONES: Record<HighlightTone, string> = {
  default: "ui:bg-primary/25",
  active: "ui:bg-primary/40 ui:ring-2 ui:ring-primary",
  "low-confidence": "ui:bg-destructive/25",
};

function percent(fraction: number): string {
  return `${fraction * 100}%`;
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
  painted,
  onClick,
}: {
  highlight: Highlight;
  active: boolean;
  painted: boolean;
  onClick?: (highlight: Highlight) => void;
}) {
  // Page fractions as percentages of the page box, so the box needs no update
  // when the zoom changes. Runtime geometry: custom properties the classes read.
  const tone: HighlightTone = active ? "active" : highlight.tone;
  const shared = {
    style: {
      "--hl-x": percent(highlight.x),
      "--hl-y": percent(highlight.y),
      "--hl-w": percent(highlight.w),
      "--hl-h": percent(highlight.h),
    },
    "data-highlight-id": highlight.id,
    "data-variant": highlight.variant,
    "data-tone": tone,
  };
  const className = cn(
    "ui:absolute ui:top-(--hl-y) ui:left-(--hl-x) ui:h-(--hl-h) ui:w-(--hl-w) ui:rounded-sm",
    painted && "ui:mix-blend-multiply",
    TONES[tone],
  );
  if (onClick === undefined) {
    return <div className={className} {...shared} />;
  }
  return (
    <button
      type="button"
      {...shared}
      aria-label={label(highlight, highlight.page + 1)}
      aria-current={active ? "true" : undefined}
      onClick={() => onClick(highlight)}
      className={cn(
        className,
        "ui:pointer-events-auto ui:cursor-pointer ui:focus-visible:focus-ring",
      )}
    />
  );
}

/** The highlights of one page, laid over it. Sized by its page, not by itself. */
export function HighlightLayer({
  highlights,
  activeId,
  onHighlightClick,
  painted = true,
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
          painted={painted}
          onClick={onHighlightClick}
        />
      ))}
    </div>
  );
}
