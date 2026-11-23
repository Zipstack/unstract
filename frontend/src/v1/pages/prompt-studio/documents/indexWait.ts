import type { IndexState } from "@v1/services/promptDocuments";

/** A document's default-profile state when indexing was asked for. */
export type IndexSnapshot = Readonly<{
  status: IndexState | undefined;
  reason: string | null;
  /** When it was asked for, in ms. */
  at: number;
}>;

/** How long a document shows processing with no change seen. */
export const INDEX_WAIT_MS = 3 * 60_000;

/**
 * Whether a document asked to index has finished, judged from the list: its
 * state or reason changed, it is gone, or the wait ran out. Re-indexing a
 * document that was already indexed changes nothing the list shows, so only
 * the wait ends it.
 */
export function isSettled(
  before: IndexSnapshot,
  now:
    | Readonly<{ status: IndexState | undefined; reason: string | null }>
    | undefined,
  at: number,
): boolean {
  return (
    now === undefined ||
    now.status !== before.status ||
    now.reason !== before.reason ||
    at - before.at >= INDEX_WAIT_MS
  );
}
