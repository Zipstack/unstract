import { useMutation } from "@tanstack/react-query";
import {
  type DocumentRef,
  selectToolDocument,
} from "@v1/services/promptDocuments";
import { useCallback, useRef, useState } from "react";

export type DocumentSelection = Readonly<{
  selectedId: string | null;
  /** Shows the document at once and saves it as the tool's; goes back to the saved one if the save fails. */
  select: (documentId: string) => void;
  /** After a removal: the removed document gives way to the first one left, which is saved. */
  removed: (documentId: string, remaining: readonly string[]) => void;
}>;

type Shown = Readonly<{
  toolId: string;
  saved: string | null;
  /** Whether the user has picked since the tool's saved document was read. */
  chosen: boolean;
  selectedId: string | null;
}>;

const fresh = (toolId: string, saved: string | null): Shown => ({
  toolId,
  saved,
  chosen: false,
  selectedId: saved,
});

/**
 * The document the workspace shows, starting from the tool's saved one
 * (`output`; an unset tool sends ""). As in v0, picking a document saves it
 * on the tool. Saves go one at a time and a superseded pick is never sent, so
 * the server ends on the last pick. A failed save goes back to the document
 * the server holds, unless a newer pick is on screen; the mutation cache
 * shows why.
 */
export function useDocumentSelection(
  toolId: string,
  savedId: string | null,
): DocumentSelection {
  const saved = savedId || null;
  const [state, setState] = useState(() => fresh(toolId, saved));
  // Another tool starts again; a saved document that arrives late is taken
  // until the user picks.
  const stale =
    state.toolId !== toolId || (!state.chosen && state.saved !== saved);
  const current = stale ? fresh(toolId, saved) : state;
  if (stale) {
    setState(current);
  }

  // Read by callbacks bound in an earlier render (a delete's onSuccess).
  const shown = useRef(current.selectedId);
  shown.current = current.selectedId;
  // What the server holds, to go back to when a save fails.
  const held = useRef(saved);
  if (!current.chosen) {
    held.current = saved;
  }
  const queue = useRef<Promise<void>>(Promise.resolve());
  const { mutateAsync } = useMutation({
    mutationFn: (params: DocumentRef) => selectToolDocument(params),
  });

  const show = useCallback((documentId: string | null) => {
    shown.current = documentId;
    setState((before) => ({ ...before, chosen: true, selectedId: documentId }));
  }, []);

  const save = useCallback(
    (documentId: string | null) => {
      queue.current = queue.current.then(async () => {
        if (shown.current !== documentId) {
          return;
        }
        try {
          await mutateAsync({ toolId, documentId: documentId ?? "" });
          held.current = documentId;
        } catch {
          if (shown.current === documentId) {
            show(held.current);
          }
        }
      });
    },
    [mutateAsync, show, toolId],
  );

  const select = useCallback(
    (documentId: string) => {
      show(documentId);
      save(documentId);
    },
    [save, show],
  );

  const removed = useCallback(
    (documentId: string, remaining: readonly string[]) => {
      if (held.current === documentId) {
        held.current = remaining[0] ?? null;
      }
      if (documentId !== shown.current) {
        return;
      }
      const next = remaining[0] ?? null;
      show(next);
      save(next);
    },
    [save, show],
  );

  return { selectedId: current.selectedId, select, removed };
}
