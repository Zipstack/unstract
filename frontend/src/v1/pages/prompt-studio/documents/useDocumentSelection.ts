import { useMutation } from "@tanstack/react-query";
import {
  type DocumentRef,
  selectToolDocument,
} from "@v1/services/promptDocuments";
import { useCallback, useState } from "react";

export type DocumentSelection = Readonly<{
  selectedId: string | null;
  /** Shows the document at once and saves it as the tool's; reverts if the save fails. */
  select: (documentId: string) => void;
  /** After a removal: the removed document gives way to the first one left, which is saved. */
  removed: (documentId: string, remaining: readonly string[]) => void;
}>;

/**
 * The document the workspace shows, starting from the tool's saved one
 * (`output`). As in v0, picking a document saves it on the tool, and a failed
 * save puts the previous one back; the mutation cache shows why.
 */
export function useDocumentSelection(
  toolId: string,
  savedId: string | null,
): DocumentSelection {
  const [selectedId, setSelectedId] = useState(savedId);
  const { mutateAsync } = useMutation({
    mutationFn: (params: DocumentRef) => selectToolDocument(params),
  });

  const select = useCallback(
    (documentId: string) => {
      const previous = selectedId;
      setSelectedId(documentId);
      // A failed save puts the previous document back, unless another choice
      // has been made since. Handled per call: a shared mutation keeps only
      // the latest call's own callbacks.
      mutateAsync({ toolId, documentId }).catch(() =>
        setSelectedId((current) =>
          current === documentId ? previous : current,
        ),
      );
    },
    [mutateAsync, selectedId, toolId],
  );

  const removed = useCallback(
    (documentId: string, remaining: readonly string[]) => {
      if (documentId !== selectedId) {
        return;
      }
      const [next] = remaining;
      if (next === undefined) {
        setSelectedId(null);
      } else {
        select(next);
      }
    },
    [select, selectedId],
  );

  return { selectedId, select, removed };
}
