import {
  classifyLoadError,
  openPdfDocument,
  type PasswordPrompt,
  pdfSourceKey,
} from "@v1/lib/pdf/pdfjs";
import type { PageSize, PdfSource } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useRef, useState } from "react";

export type PdfDocumentState =
  | { status: "empty" }
  | { status: "loading" }
  | { status: "password"; incorrect: boolean }
  | { status: "unsupported" }
  | { status: "failed"; message: string }
  | {
      status: "ready";
      document: PDFDocumentProxy;
      pageSizes: readonly PageSize[];
    };

export interface PdfDocumentHandle {
  state: PdfDocumentState;
  /** Opens the same source again, after a failure. */
  retry: () => void;
  /**
   * Gives the password the document asked for. The load carries on where it
   * stopped; nothing is downloaded again.
   */
  submitPassword: (password: string) => void;
}

/** One open attempt. A new object means a new attempt, even for the same source. */
interface OpenRequest {
  key: string;
  source: PdfSource | null;
}

/**
 * Opens a PDF and tracks it through loading, failure, password and ready.
 *
 * The source may be a new object on every render: it reopens only when its
 * URL, request options or bytes change (see `pdfSourceKey`). The previous
 * load is destroyed when the source changes or the component unmounts.
 */
export function usePdfDocument(source: PdfSource | null): PdfDocumentHandle {
  const key = pdfSourceKey(source);
  const [request, setRequest] = useState<OpenRequest>({ key, source });
  const [result, setResult] = useState<{
    request: OpenRequest;
    state: PdfDocumentState;
  } | null>(null);
  // The prompt the shown password state answers, with the attempt it belongs to.
  const promptRef = useRef<{
    request: OpenRequest;
    prompt: PasswordPrompt;
  } | null>(null);

  let current = request;
  if (request.key !== key) {
    // Adjusting state during render: the new source wins before any effect runs.
    current = { key, source };
    setRequest(current);
  }

  useEffect(() => {
    if (request.source === null) {
      return;
    }
    let live = true;
    const opening = openPdfDocument(request.source, {
      onPassword(prompt) {
        if (!live) {
          return;
        }
        promptRef.current = { request, prompt };
        setResult({
          request,
          state: { status: "password", incorrect: prompt.incorrect },
        });
      },
    });
    opening.promise.then(
      ({ document, pageSizes }) => {
        if (!live) {
          return;
        }
        const state: PdfDocumentState =
          pageSizes.length === 0
            ? { status: "empty" }
            : { status: "ready", document, pageSizes };
        setResult({ request, state });
      },
      (error: unknown) => {
        if (!live) {
          return;
        }
        const failure = classifyLoadError(error);
        const state: PdfDocumentState =
          failure.kind === "password"
            ? { status: "password", incorrect: failure.incorrect }
            : failure.kind === "unsupported"
              ? { status: "unsupported" }
              : { status: "failed", message: failure.message };
        setResult({ request, state });
      },
    );
    return () => {
      live = false;
      if (promptRef.current?.request === request) {
        promptRef.current = null;
      }
      opening.destroy();
    };
  }, [request]);

  const retry = useCallback(() => {
    setRequest((previous) => ({ ...previous }));
  }, []);
  const submitPassword = useCallback((password: string) => {
    const pending = promptRef.current;
    if (pending === null) {
      return;
    }
    // A prompt answers once; pdf.js asks again if the password is wrong.
    promptRef.current = null;
    setResult({ request: pending.request, state: { status: "loading" } });
    pending.prompt.submit(password);
  }, []);

  let state: PdfDocumentState;
  if (current.source === null) {
    state = { status: "empty" };
  } else if (result?.request === current) {
    state = result.state;
  } else {
    state = { status: "loading" };
  }
  return { state, retry, submitPassword };
}
