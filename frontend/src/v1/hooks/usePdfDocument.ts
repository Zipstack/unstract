import {
  classifyLoadError,
  openPdfDocument,
  pdfSourceKey,
} from "@v1/lib/pdf/pdfjs";
import type { PageSize, PdfSource } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useState } from "react";

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
  /** Opens the same source with a password, after a password state. */
  submitPassword: (password: string) => void;
}

/** One open attempt. A new object means a new attempt, even for the same source. */
interface Request {
  key: string;
  source: PdfSource | null;
  password?: string;
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
  const [request, setRequest] = useState<Request>({ key, source });
  const [result, setResult] = useState<{
    request: Request;
    state: PdfDocumentState;
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
    const opening = openPdfDocument(request.source, {
      password: request.password,
    });
    let live = true;
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
      opening.destroy();
    };
  }, [request]);

  const retry = useCallback(() => {
    setRequest((previous) => ({ ...previous }));
  }, []);
  const submitPassword = useCallback((password: string) => {
    setRequest((previous) => ({ ...previous, password }));
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
