/*
 * Recovery from a stale code chunk after a deploy: the browser's page names a
 * hashed file the server no longer has. Mirrors v0's handleRouteError
 * (components/error/LazyOutlet), which v1 may not import.
 */

const RELOAD_KEY = "unstract.v1.chunkReloadAt";
const RELOAD_WINDOW_MS = 10_000;

/** A failed dynamic import; matching is best-effort across browsers. */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const { message } = error;
  return (
    error.name === "ChunkLoadError" ||
    message.includes("Failed to fetch dynamically imported module") ||
    message.includes("error loading dynamically imported module") ||
    message.includes("Importing a module script failed")
  );
}

/**
 * Reloads once to fetch the new deploy's chunks. A repeat failure within ten
 * seconds does not reload again, so a chunk that is really gone shows the
 * manual fallback instead of looping. True when it reloaded.
 */
export function reloadOnce(
  storage: Pick<Storage, "getItem" | "setItem"> | null,
  reload: () => void,
  now: number = Date.now(),
): boolean {
  try {
    const last = Number(storage?.getItem(RELOAD_KEY) ?? 0);
    if (!storage || now - last <= RELOAD_WINDOW_MS) {
      return false;
    }
    storage.setItem(RELOAD_KEY, String(now));
  } catch {
    return false; // no session storage: leave recovery to the fallback
  }
  reload();
  return true;
}
