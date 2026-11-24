import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "@v1/lib/notify";
import {
  promptDocumentKeys,
  type UploadedDocument,
  type UploadParams,
  uploadPromptDocument,
} from "@v1/services/promptDocuments";
import { reportApiError } from "@v1/services/report";
import { useCallback, useEffect, useRef, useState } from "react";
import { planUploads, type UploadPolicy } from "./uploadPolicy";

/** A file waiting for, or in, its upload. */
export type UploadRow = Readonly<{
  key: string;
  file: File;
  /** Bytes sent so far. */
  loaded: number;
  started: boolean;
}>;

export type UseUploadsOptions = Readonly<{
  toolId: string;
  policy: UploadPolicy;
  /** Names already in the list; a file with one of them is refused. */
  existingNames: readonly string[];
  onUploaded?: (document: UploadedDocument) => void;
}>;

export type Uploads = Readonly<{
  rows: readonly UploadRow[];
  add: (files: readonly File[]) => void;
}>;

/**
 * Uploads files one at a time, so each row shows its own progress. Refused
 * files never start: each gets a toast saying why. A failed upload is
 * reported by the app's mutation handler (a toast with the request id) and its
 * row goes; the next file still uploads. The state belongs to one tool: the
 * panel mounts it afresh for another.
 */
export function useUploads({
  toolId,
  policy,
  existingNames,
  onUploaded,
}: UseUploadsOptions): Uploads {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<readonly UploadRow[]>([]);
  const pending = useRef<UploadRow[]>([]);
  const busy = useRef(false);
  const nextKey = useRef(0);
  // The queue drains after an unmount (each file belongs to its tool), but a
  // panel that has gone is not told: its callbacks belong to another screen.
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const { mutateAsync } = useMutation({
    mutationFn: (params: UploadParams) => uploadPromptDocument(params),
  });

  const patch = useCallback(
    (key: string, change: Partial<UploadRow>) =>
      setRows((current) =>
        current.map((row) => (row.key === key ? { ...row, ...change } : row)),
      ),
    [],
  );

  const pump = useCallback(async () => {
    if (busy.current) {
      return;
    }
    busy.current = true;
    // The list this tool's uploads land in, read while the page is still on it.
    const listKey = promptDocumentKeys.list(toolId);
    try {
      for (
        let row = pending.current.shift();
        row;
        row = pending.current.shift()
      ) {
        const { key, file } = row;
        patch(key, { started: true });
        let document: UploadedDocument | null = null;
        try {
          document = await mutateAsync({
            toolId,
            file,
            onProgress: (loaded) => patch(key, { loaded }),
          });
        } catch {
          // Already shown: the mutation cache reports every failed mutation.
        }
        // Read the list either way: a failed answer can follow a stored file.
        await queryClient.invalidateQueries({ queryKey: listKey });
        setRows((current) =>
          current.filter((candidate) => candidate.key !== key),
        );
        if (document && mounted.current) {
          try {
            onUploaded?.(document);
          } catch (error) {
            // The workspace's callback failing must not strand the queue.
            reportApiError(error);
          }
        }
      }
    } finally {
      busy.current = false;
    }
  }, [mutateAsync, onUploaded, patch, queryClient, toolId]);

  const add = useCallback(
    (files: readonly File[]) => {
      const queuedNames = [
        ...pending.current.map((row) => row.file.name),
        ...rows.map((row) => row.file.name),
      ];
      const plan = planUploads(files, policy, [
        ...existingNames,
        ...queuedNames,
      ]);
      for (const { name, reason } of plan.refused) {
        toast.error(`${name} was not uploaded`, { description: reason });
      }
      const added = plan.accepted.map((file) => ({
        key: `upload-${nextKey.current++}`,
        file,
        loaded: 0,
        started: false,
      }));
      if (added.length === 0) {
        return;
      }
      pending.current.push(...added);
      setRows((current) => [...current, ...added]);
      void pump();
    },
    [existingNames, policy, pump, rows],
  );

  return { rows, add };
}
