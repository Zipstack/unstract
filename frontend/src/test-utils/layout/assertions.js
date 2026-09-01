import { expect } from "vitest";

// Subpixel rounding only. Anything a real layout bug produces is orders of
// magnitude larger (the column drift that motivated these helpers was 181px),
// so a tight epsilon costs nothing and keeps the assertions meaningful.
export const EPSILON = 1.5;

const box = (el) => el.getBoundingClientRect();

const describeAll = (elements, pick) =>
  elements
    .map((el, i) => `  [${i}] ${Math.round(pick(box(el)))}px  ${text(el)}`)
    .join("\n");

const text = (el) => {
  const raw = (el.textContent || "").trim().replace(/\s+/g, " ");
  return raw.length > 40 ? `${raw.slice(0, 40)}…` : raw;
};

/**
 * Every element starts at the same x — i.e. they read as a column.
 *
 * This is the assertion that survives redesigns: it says nothing about where
 * the column is, only that it is straight. Padding, fonts and design tokens
 * can all change without touching it; only a column that sizes itself to its
 * own content breaks it.
 */
export const expectAlignedX = (elements, label) => {
  expect(elements.length, `${label}: nothing to align`).toBeGreaterThan(1);
  const xs = elements.map((el) => box(el).x);
  const spread = Math.max(...xs) - Math.min(...xs);
  expect(
    spread,
    `${label}: expected one straight column, got ${spread.toFixed(1)}px of drift\n${describeAll(elements, (b) => b.x)}`,
  ).toBeLessThanOrEqual(EPSILON);
};

/** `child` stays inside `parent` horizontally. */
export const expectContained = (child, parent, label) => {
  const c = box(child);
  const p = box(parent);
  const overflow = Math.max(p.left - c.left, c.right - p.right);
  expect(
    overflow,
    `${label}: child escapes its container by ${overflow.toFixed(1)}px — a rigid child inside a shrinkable box spills instead of shrinking with it\n  child  ${Math.round(c.left)}→${Math.round(c.right)}  ${text(child)}\n  parent ${Math.round(p.left)}→${Math.round(p.right)}`,
  ).toBeLessThanOrEqual(EPSILON);
};

/** `leftEl` ends before `rightEl` begins — they never sit on top of each other. */
export const expectNoHorizontalOverlap = (leftEl, rightEl, label) => {
  const a = box(leftEl);
  const b = box(rightEl);
  const overlap = a.right - b.left;
  expect(
    overlap,
    `${label}: elements overlap by ${overlap.toFixed(1)}px\n  ${Math.round(a.left)}→${Math.round(a.right)}  ${text(leftEl)}\n  ${Math.round(b.left)}→${Math.round(b.right)}  ${text(rightEl)}`,
  ).toBeLessThanOrEqual(EPSILON);
};

/** Content fits the element instead of forcing it wider. */
export const expectNoHorizontalOverflow = (el, label) => {
  const overflow = el.scrollWidth - el.clientWidth;
  expect(
    overflow,
    `${label}: content is ${overflow}px wider than its box\n  ${text(el)}`,
  ).toBeLessThanOrEqual(1);
};

/** Truncation engaged — the layout absorbed the content, not the reverse. */
export const expectTruncated = (el, label) => {
  expect(
    el.scrollWidth,
    `${label}: expected the text to be clipped and tooltip-backed, but it fits — the fixture no longer exercises overflow\n  ${text(el)}`,
  ).toBeGreaterThan(el.clientWidth);
};
