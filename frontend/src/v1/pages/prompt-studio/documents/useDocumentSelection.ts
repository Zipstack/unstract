import { useMutation } from "@tanstack/react-query";
import {
  type DocumentRef,
  selectToolDocument,
} from "@v1/services/promptDocuments";
import { useCallback, useRef, useState } from "react";

export type DocumentSelection = Readonly<{
  selectedId: string | null;
  /** Shows the document at once and saves it as the tool's; goes back to the last saved one if the save fails. */
  select: (documentId: string) => void;
  /**
   * After a removal: if it was the shown document, the first one left is
   * shown and saved, or the saved document is cleared when none is left.
   */
  removed: (documentId: string, remaining: readonly string[]) => void;
}>;

type Shown = Readonly<{
  toolId: string;
  saved: string | null;
  /** Whether the user has picked since the tool's saved document was read. */
  chosen: boolean;
  selectedId: string | null;
}>;

type Held = Readonly<{
  toolId: string;
  id: string | null;
  epoch: number;
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
 * on the tool. Saves go one at a time, and a pick replaced while it is still
 * queued is skipped. A failed save goes back to the last document saved (after
 * a removal of the shown one, the first one left), unless a newer pick is on
 * screen; the mutation cache shows why.
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
  // What the server holds, to go back to when a save fails. A tool switch
  // or a removal starts a new epoch, so a save that lands later from before
  // it cannot set a document of another tool, or a removed one.
  const held = useRef<Held>({ toolId, id: saved, epoch: 0 });
  if (held.current.toolId !== toolId) {
    held.current = { toolId, id: saved, epoch: held.current.epoch + 1 };
  } else if (!current.chosen && held.current.id !== saved) {
    held.current = { ...held.current, id: saved };
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
        const { epoch } = held.current;
        try {
          await mutateAsync({ toolId, documentId: documentId ?? "" });
          if (held.current.epoch === epoch) {
            held.current = { ...held.current, id: documentId };
          }
        } catch {
          if (shown.current === documentId) {
            show(held.current.id);
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
      const next = remaining[0] ?? null;
      const gone =
        held.current.id === documentId || shown.current === documentId;
      held.current = {
        ...held.current,
        id: gone ? next : held.current.id,
        epoch: held.current.epoch + 1,
      };
      if (documentId !== shown.current) {
        return;
      }
      show(next);
      save(next);
    },
    [save, show],
  );

  return { selectedId: current.selectedId, select, removed };
}
