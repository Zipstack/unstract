/*
 * The one place v1 touches pdf.js. Everything else imports from here, so the
 * version, the build and the security defaults are decided once.
 *
 * It uses the legacy build of the pdfjs-dist already in package.json (3.11.174,
 * shared with v0): the default build targets only the newest browsers. The
 * worker is bundled with `?url`, never fetched from a CDN. Both load on first
 * use, so pdf.js stays out of the bundle of any page that never opens a PDF.
 */
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  PDFPageProxy,
} from "pdfjs-dist";
import type { DocumentInitParameters } from "pdfjs-dist/types/src/display/api";
import type { OpenedPdf, PageSize, PdfLoadFailure, PdfSource } from "./types";

type Pdfjs = typeof import("pdfjs-dist/legacy/build/pdf.js");

/** How many page sizes are requested from the worker at once. */
const PAGE_SIZE_CONCURRENCY = 16;

let pdfjsPromise: Promise<Pdfjs> | null = null;

/** Loads pdf.js and points it at the bundled worker, once per page load. */
export function loadPdfjs(): Promise<Pdfjs> {
  pdfjsPromise ??= Promise.all([
    import("pdfjs-dist/legacy/build/pdf.js"),
    import("pdfjs-dist/legacy/build/pdf.worker.min.js?url"),
  ]).then(
    ([pdfjs, worker]) => {
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
      return pdfjs;
    },
    (error: unknown) => {
      // A failed chunk load (offline, a deploy in between) must not stick:
      // Retry has to be able to try again.
      pdfjsPromise = null;
      throw error;
    },
  );
  return pdfjsPromise;
}

/**
 * The `getDocument` parameters for a source. `isEvalSupported` is always false
 * (CVE-2024-4367: 3.x can be made to evaluate a font's code). In-memory bytes
 * are copied, because pdf.js transfers the buffer it gets to its worker, which
 * would leave the caller's copy empty for the next attempt.
 */
export function toDocumentParams(
  source: PdfSource,
  password?: string,
): DocumentInitParameters {
  const shared = { isEvalSupported: false, password };
  if (source.kind === "url") {
    return {
      ...shared,
      url: source.url,
      withCredentials: source.withCredentials ?? false,
      httpHeaders: source.httpHeaders ? { ...source.httpHeaders } : undefined,
    };
  }
  const bytes =
    source.data instanceof Uint8Array
      ? source.data.slice()
      : new Uint8Array(source.data.slice(0));
  return { ...shared, data: bytes };
}

const dataSourceIds = new WeakMap<object, number>();
let nextDataSourceId = 0;

/**
 * A key that changes only when the document would: the URL and request options
 * for a URL, the buffer's identity for bytes. Lets a caller pass a fresh object
 * on every render without reopening the document.
 */
export function pdfSourceKey(source: PdfSource | null): string {
  if (source === null) {
    return "none";
  }
  if (source.kind === "url") {
    const headers = Object.entries(source.httpHeaders ?? {}).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    return JSON.stringify([
      "url",
      source.url,
      source.withCredentials ?? false,
      headers,
    ]);
  }
  let id = dataSourceIds.get(source.data);
  if (id === undefined) {
    id = nextDataSourceId++;
    dataSourceIds.set(source.data, id);
  }
  return `data:${id}`;
}

function pageSize(page: PDFPageProxy): PageSize {
  const { width, height } = page.getViewport({ scale: 1 });
  return { width, height };
}

/**
 * Every page's size, in page order. Requests run in parallel (bounded), not one
 * after another: one at a time took about a second for 200 pages.
 */
export async function readPageSizes(
  document: PDFDocumentProxy,
  concurrency: number = PAGE_SIZE_CONCURRENCY,
): Promise<PageSize[]> {
  const sizes = new Array<PageSize>(document.numPages);
  let next = 0;
  async function drain(): Promise<void> {
    while (next < document.numPages) {
      const index = next++;
      sizes[index] = pageSize(await document.getPage(index + 1));
    }
  }
  const lanes = Math.max(1, Math.min(concurrency, document.numPages));
  await Promise.all(Array.from({ length: lanes }, drain));
  return sizes;
}

/** Maps a pdf.js load error to what the viewer shows. */
export function classifyLoadError(error: unknown): PdfLoadFailure {
  const name =
    typeof error === "object" && error !== null && "name" in error
      ? String(error.name)
      : "";
  if (name === "PasswordException") {
    // pdf.js PasswordResponses: 1 needs a password, 2 the one given was wrong.
    const code = (error as { code?: unknown }).code;
    return { kind: "password", incorrect: code === 2 };
  }
  if (name === "InvalidPDFException") {
    return { kind: "unsupported" };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { kind: "failed", message };
}

export interface PdfOpening {
  readonly promise: Promise<OpenedPdf>;
  /** Stops the load and frees the document and its worker. Safe to call twice. */
  destroy(): void;
}

/** Opens a document and reads its page sizes. Call `destroy` when done with it. */
export function openPdfDocument(
  source: PdfSource,
  options: { password?: string } = {},
): PdfOpening {
  let task: PDFDocumentLoadingTask | null = null;
  let destroyed = false;
  const promise = (async () => {
    const pdfjs = await loadPdfjs();
    if (destroyed) {
      throw new Error("The document was closed before it opened.");
    }
    task = pdfjs.getDocument(toDocumentParams(source, options.password));
    const document = await task.promise;
    const pageSizes = await readPageSizes(document);
    return { document, pageSizes };
  })();
  return {
    promise,
    destroy() {
      if (destroyed) {
        return;
      }
      destroyed = true;
      // Destroying the loading task also destroys its document.
      void task?.destroy();
    },
  };
}
