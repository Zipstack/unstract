let measured: number | null = null;

/**
 * The width of a classic vertical scrollbar on this platform, in CSS px: 0
 * with overlay scrollbars (macOS, mobile), usually 15 to 17 elsewhere.
 * Measured once with an off-screen probe, so nothing has to guess it.
 */
export function scrollbarWidth(doc: Document = document): number {
  if (measured !== null) {
    return measured;
  }
  const body = doc.body;
  if (!body) {
    return 0;
  }
  const probe = doc.createElement("div");
  // A probe, not page styling: it never paints and is removed at once.
  probe.style.cssText =
    "position:absolute;top:-9999px;width:100px;height:100px;overflow:scroll;visibility:hidden";
  body.appendChild(probe);
  measured = Math.max(0, probe.offsetWidth - probe.clientWidth);
  probe.remove();
  return measured;
}

/** Forgets the measurement. For tests. */
export function resetScrollbarWidth(): void {
  measured = null;
}
