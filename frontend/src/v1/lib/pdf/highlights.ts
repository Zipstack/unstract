/*
 * Highlights in one shape, whatever produced them. Every position is a fraction
 * of the page box (0 to 1, from the top-left), so a highlight stays on its text
 * at any zoom without being recomputed.
 *
 * Input shapes:
 *
 * - Line entry, LLMWhisperer `line_metadata[*].raw` (Prompt Studio, HITL):
 *   `[page, base_y, height, page_height, line_confidence?]`. `base_y` is the
 *   line's baseline, so the box runs from `base_y - height` down to `base_y`,
 *   across the full width. `line_confidence` is a number when sent.
 * - Line entry with a word box in place of the confidence:
 *   `[page, y, height, page_height, {offset, width, page_width?}]`. The agentic
 *   table worker sends this today, with `page_width`; v0 HITL used to build it
 *   from `confidence_metadata`, without one.
 * - Word boxes, LLMWhisperer `confidence_metadata`: `{text, confidence, offset,
 *   width}`, only for words below 0.9 confidence. They carry no y: they sit on
 *   their line, so they are passed with it (`normaliseWords`).
 * - Agentic Prompt Studio: `[page, left%, top%, width%, height%, hasMetadata]`,
 *   already in percentages of the page.
 *
 * Pages are 0-based everywhere, as the producers send them.
 */
import type { PageSize } from "./types";

export type HighlightVariant = "line" | "box";
export type HighlightTone = "default" | "active" | "low-confidence";

export interface Highlight {
  id: string;
  /** 0-based page index. */
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
  variant: HighlightVariant;
  tone: HighlightTone;
  /** 0 to 1, when the producer sent one. */
  confidence?: number;
}

/** A word's horizontal extent, in the same page-image units as its line. */
export interface WordBox {
  offset: number;
  width: number;
  /** The page width in those units. Absent from LLMWhisperer's own output. */
  page_width?: number;
  text?: string;
  confidence?: number;
}

export interface NormaliseOptions {
  /** PDF page sizes, used to find a page's width when a word box lacks one. */
  pageSizes?: readonly PageSize[];
  /** Prefix for generated ids; the entry's position is appended. */
  idPrefix?: string;
  /** Confidence below this is shown as low. LLMWhisperer reports words below 0.9. */
  lowConfidenceBelow?: number;
}

export const LOW_CONFIDENCE_BELOW = 0.9;

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isWordBox(value: unknown): value is WordBox {
  return (
    typeof value === "object" &&
    value !== null &&
    isFiniteNumber((value as WordBox).offset) &&
    isFiniteNumber((value as WordBox).width)
  );
}

function toneFor(
  confidence: number | undefined,
  options: NormaliseOptions,
): HighlightTone {
  const threshold = options.lowConfidenceBelow ?? LOW_CONFIDENCE_BELOW;
  return confidence !== undefined && confidence < threshold
    ? "low-confidence"
    : "default";
}

/** A box with its edges clamped to the page; null when nothing is left of it. */
function boxOnPage(
  x: number,
  y: number,
  w: number,
  h: number,
): { x: number; y: number; w: number; h: number } | null {
  const left = clamp01(x);
  const top = clamp01(y);
  const right = clamp01(x + w);
  const bottom = clamp01(y + h);
  if (right <= left || bottom <= top) {
    return null;
  }
  return { x: left, y: top, w: right - left, h: bottom - top };
}

/** A box spanning the page's width reads as a line, whatever produced it. */
function variantOf(box: { x: number; w: number }): HighlightVariant {
  return box.x <= 0.001 && box.w >= 0.999 ? "line" : "box";
}

interface LineGeometry {
  page: number;
  baseY: number;
  height: number;
  pageHeight: number;
  extra: unknown;
}

/** The four leading numbers of a line entry; null for padding and junk. */
function readLine(entry: unknown): LineGeometry | null {
  if (!Array.isArray(entry) || entry.length < 4) {
    return null;
  }
  const [page, baseY, height, pageHeight, extra] = entry as unknown[];
  if (
    !isFiniteNumber(page) ||
    !isFiniteNumber(baseY) ||
    !isFiniteNumber(height) ||
    !isFiniteNumber(pageHeight) ||
    page < 0 ||
    pageHeight <= 0 ||
    height <= 0
  ) {
    // Producers pad with [0, 0, 0, 0] (and zero-height separators) for lines
    // that have no place on the page.
    return null;
  }
  return { page: Math.trunc(page), baseY, height, pageHeight, extra };
}

/**
 * The page's width in the line's units: the producer's when sent, otherwise
 * from the PDF page's aspect ratio. Dividing by the page height instead, as v0
 * did, puts every word box too far left on a portrait page.
 */
function pageWidthUnits(
  line: LineGeometry,
  word: WordBox,
  options: NormaliseOptions,
): number | null {
  if (isFiniteNumber(word.page_width) && word.page_width > 0) {
    return word.page_width;
  }
  const size = options.pageSizes?.[line.page];
  if (!size || size.height <= 0) {
    return null;
  }
  return line.pageHeight * (size.width / size.height);
}

function wordHighlight(
  line: LineGeometry,
  word: WordBox,
  id: string,
  options: NormaliseOptions,
): Highlight | null {
  const pageWidth = pageWidthUnits(line, word, options);
  if (pageWidth === null) {
    return null;
  }
  const box = boxOnPage(
    word.offset / pageWidth,
    (line.baseY - line.height) / line.pageHeight,
    word.width / pageWidth,
    line.height / line.pageHeight,
  );
  if (box === null) {
    return null;
  }
  const confidence = isFiniteNumber(word.confidence)
    ? word.confidence
    : undefined;
  return {
    id,
    page: line.page,
    ...box,
    variant: variantOf(box),
    tone: toneFor(confidence, options),
    confidence,
  };
}

/** One line entry, as a full-width line or, with a word box, as that box. */
export function normaliseLine(
  entry: unknown,
  id: string,
  options: NormaliseOptions = {},
): Highlight | null {
  const line = readLine(entry);
  if (line === null) {
    return null;
  }
  if (isWordBox(line.extra)) {
    return wordHighlight(line, line.extra, id, options);
  }
  const box = boxOnPage(
    0,
    (line.baseY - line.height) / line.pageHeight,
    1,
    line.height / line.pageHeight,
  );
  if (box === null) {
    return null;
  }
  const confidence = isFiniteNumber(line.extra) ? line.extra : undefined;
  return {
    id,
    page: line.page,
    ...box,
    variant: "line",
    tone: toneFor(confidence, options),
    confidence,
  };
}

/** Line entries, as sent for one field or prompt. Padding entries are dropped. */
export function normaliseLines(
  entries: readonly unknown[],
  options: NormaliseOptions = {},
): Highlight[] {
  const prefix = options.idPrefix ?? "line-";
  const highlights: Highlight[] = [];
  entries.forEach((entry, index) => {
    const highlight = normaliseLine(entry, `${prefix}${index}`, options);
    if (highlight !== null) {
      highlights.push(highlight);
    }
  });
  return highlights;
}

/** LLMWhisperer word boxes on one line, as boxes. Needs page sizes or `page_width`. */
export function normaliseWords(
  lineEntry: unknown,
  words: readonly unknown[],
  options: NormaliseOptions = {},
): Highlight[] {
  const line = readLine(lineEntry);
  if (line === null) {
    return [];
  }
  const prefix = options.idPrefix ?? "word-";
  const highlights: Highlight[] = [];
  words.forEach((word, index) => {
    if (!isWordBox(word)) {
      return;
    }
    const highlight = wordHighlight(line, word, `${prefix}${index}`, options);
    if (highlight !== null) {
      highlights.push(highlight);
    }
  });
  return highlights;
}

/** Agentic Prompt Studio entries, `[page, left%, top%, width%, height%, hasMetadata]`. */
export function normaliseAgentic(
  entries: readonly unknown[],
  options: Pick<NormaliseOptions, "idPrefix"> = {},
): Highlight[] {
  const prefix = options.idPrefix ?? "agentic-";
  const highlights: Highlight[] = [];
  entries.forEach((entry, index) => {
    if (!Array.isArray(entry) || entry.length < 5) {
      return;
    }
    // The 6th element, hasMetadata, says only that a word box was sent; the
    // geometry already shows whether it spans the line.
    const [page, left, top, width, height] = entry as unknown[];
    if (
      !isFiniteNumber(page) ||
      page < 0 ||
      !isFiniteNumber(left) ||
      !isFiniteNumber(top) ||
      !isFiniteNumber(width) ||
      !isFiniteNumber(height)
    ) {
      return;
    }
    const box = boxOnPage(left / 100, top / 100, width / 100, height / 100);
    if (box === null) {
      return;
    }
    highlights.push({
      id: `${prefix}${index}`,
      page: Math.trunc(page),
      ...box,
      variant: variantOf(box),
      tone: "default",
    });
  });
  return highlights;
}

/** Highlights grouped by 0-based page, in their original order. */
export function highlightsByPage(
  highlights: readonly Highlight[],
): Map<number, Highlight[]> {
  const pages = new Map<number, Highlight[]>();
  for (const highlight of highlights) {
    const list = pages.get(highlight.page);
    if (list) {
      list.push(highlight);
    } else {
      pages.set(highlight.page, [highlight]);
    }
  }
  return pages;
}
