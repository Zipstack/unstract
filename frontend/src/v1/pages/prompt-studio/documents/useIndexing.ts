import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type DocumentRef,
  indexPromptDocument,
  type PromptDocument,
  promptDocumentKeys,
} from "@v1/services/promptDocuments";
import { useCallback, useMemo, useState } from "react";
import { defaultIndexStatus } from "./documentFacts";
import { type IndexSnapshot, isSettled } from "./indexWait";

/** How often the list is read again while a document indexes. */
export const INDEX_POLL_MS = 5000;

export type Indexing = Readonly<{
  /** Ids asked to index here that have not finished. */
  ids: ReadonlySet<string>;
  request: (document: PromptDocument) => void;
  /** Ends the waits a fresh list shows have finished. */
  settle: (documents: readonly PromptDocument[] | undefined) => void;
}>;

function snapshot(document: PromptDocument | undefined) {
  const status = document ? defaultIndexStatus(document) : undefined;
  return document
    ? { status: status?.status, reason: status?.failure_reason ?? null }
    : undefined;
}

/*
 * ponytail: the index result arrives on the Prompt Studio socket
 * (`index_document`, owned by the run engine). Until the frame passes those
 * ids in, a document asked to index here shows Processing while the list is
 * polled, and stops when its state or reason changes, or after a wait. Once
 * the socket's ids arrive, `request` only sends the index request: the poll,
 * `settle` and the wait go, and the frame invalidates the list and EXTRACT.
 */
export function useIndexing(toolId: string): Indexing {
  const queryClient = useQueryClient();
  const [asked, setAsked] = useState<ReadonlyMap<string, IndexSnapshot>>(
    () => new Map(),
  );
  const { mutateAsync } = useMutation({
    mutationFn: (params: DocumentRef) => indexPromptDocument(params),
  });

  const forget = useCallback((ids: readonly string[]) => {
    setAsked((current) => {
      const next = new Map(current);
      for (const id of ids) {
        next.delete(id);
      }
      return next;
    });
  }, []);

  const request = useCallback(
    (document: PromptDocument) => {
      const id = document.document_id;
      const before = snapshot(document);
      setAsked((current) =>
        new Map(current).set(id, {
          status: before?.status,
          reason: before?.reason ?? null,
          at: Date.now(),
        }),
      );
      // Awaited per call, not through mutate's onError: a shared mutation keeps
      // only the latest call's callbacks, so an earlier failure would be lost.
      // The mutation cache shows the error; here the row stops processing.
      mutateAsync({ toolId, documentId: id }).catch(() => forget([id]));
    },
    [forget, mutateAsync, toolId],
  );

  const settle = useCallback(
    (documents: readonly PromptDocument[] | undefined) => {
      if (!documents || asked.size === 0) {
        return;
      }
      const now = Date.now();
      const done = [...asked].flatMap(([id, before]) =>
        isSettled(
          before,
          snapshot(documents.find((document) => document.document_id === id)),
          now,
        )
          ? [id]
          : [],
      );
      if (done.length === 0) {
        return;
      }
      forget(done);
      for (const documentId of done) {
        // The extracted text may have changed with the new index.
        void queryClient.invalidateQueries({
          queryKey: promptDocumentKeys.content({
            toolId,
            documentId,
            view: "EXTRACT",
          }),
        });
      }
    },
    [asked, forget, queryClient, toolId],
  );

  const ids = useMemo(() => new Set(asked.keys()), [asked]);
  return { ids, request, settle };
}
