/*
 * The one place v1 touches pdf.js. Everything else imports from here, so the
 * version, the build and the security defaults are decided once.
 *
 * It uses the same pdf.js as v0: the default build and worker of the
 * pdfjs-dist already in package.json (3.11.174), so the app ships one engine
 * and one worker. The worker is bundled with `?url`, never fetched from a CDN.
 * Both load on first use, so pdf.js stays out of the bundle of any page that
 * never opens a PDF.
 */
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  PDFPageProxy,
} from "pdfjs-dist";
import type { DocumentInitParameters } from "pdfjs-dist/types/src/display/api";
import type { OpenedPdf, PageSize, PdfLoadFailure, PdfSource } from "./types";

type Pdfjs = typeof import("pdfjs-dist");

/** How many page sizes are requested from the worker at once. */
const PAGE_SIZE_CONCURRENCY = 16;

let pdfjsPromise: Promise<Pdfjs> | null = null;

/** Loads pdf.js and points it at the bundled worker, once per page load. */
export function loadPdfjs(): Promise<Pdfjs> {
  pdfjsPromise ??= Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.js?url"),
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
export function toDocumentParams(source: PdfSource): DocumentInitParameters {
  const shared = { isEvalSupported: false };
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

const objectKeys = new WeakMap<object, number>();
let nextObjectKey = 0;

/**
 * A number for an object's identity, the same for as long as the object
 * lives. The one notion of identity for documents and byte sources.
 */
export function objectKey(value: object): number {
  let key = objectKeys.get(value);
  if (key === undefined) {
    key = nextObjectKey++;
    objectKeys.set(value, key);
  }
  return key;
}

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
  return `data:${objectKey(source.data)}`;
}

function pageSize(page: PDFPageProxy): PageSize {
  const { width, height } = page.getViewport({ scale: 1 });
  return { width, height };
}

/** US Letter, for a page whose size cannot be read when no other page's can. */
const FALLBACK_PAGE_SIZE: PageSize = { width: 612, height: 792 };

/**
 * Every page's size, in page order. Requests run in parallel (bounded), not one
 * after another: one at a time took about a second for 200 pages.
 *
 * A page whose size cannot be read takes the size of the nearest readable page
 * before it (or after it, for the first pages), so one damaged page does not
 * stop the rest of the document from opening; that page then fails on its own
 * when it renders. Only when no page can be read does the whole read fail.
 */
export async function readPageSizes(
  document: PDFDocumentProxy,
  concurrency: number = PAGE_SIZE_CONCURRENCY,
): Promise<PageSize[]> {
  const read = new Array<PageSize | null>(document.numPages).fill(null);
  let firstError: unknown = null;
  let next = 0;
  async function drain(): Promise<void> {
    while (next < document.numPages) {
      const index = next++;
      try {
        read[index] = pageSize(await document.getPage(index + 1));
      } catch (error) {
        firstError ??= error;
        console.error(`pdf.js could not read page ${index + 1}`, error);
      }
    }
  }
  const lanes = Math.max(1, Math.min(concurrency, document.numPages));
  await Promise.all(Array.from({ length: lanes }, drain));
  if (document.numPages > 0 && read.every((size) => size === null)) {
    throw firstError;
  }
  let previous: PageSize =
    read.find((size): size is PageSize => size !== null) ?? FALLBACK_PAGE_SIZE;
  return read.map((size) => {
    previous = size ?? previous;
    return previous;
  });
}

/** The `name` pdf.js gives an error (`PasswordException`, …), or "". */
export function pdfErrorName(error: unknown): string {
  return typeof error === "object" && error !== null && "name" in error
    ? String(error.name)
    : "";
}

/** Whether a render task ended because it was cancelled, not because it failed. */
export function isRenderCancelled(error: unknown): boolean {
  return pdfErrorName(error) === "RenderingCancelledException";
}

/** Maps a pdf.js load error to what the viewer shows. */
export function classifyLoadError(error: unknown): PdfLoadFailure {
  const name = pdfErrorName(error);
  if (name === "PasswordException") {
    // pdf.js PasswordResponses: 1 needs a password, 2 the one given was wrong.
    const code = (error as { code?: unknown }).code;
    return { kind: "password", incorrect: code === 2 };
  }
  if (name === "InvalidPDFException") {
    return { kind: "unsupported" };
  }
  // pdf.js puts the full URL in these messages, and a signed URL carries its
  // token there: build the message from the status instead of showing it.
  if (name === "MissingPDFException") {
    return { kind: "failed", message: "The document wasn't found." };
  }
  if (name === "UnexpectedResponseException") {
    const status = (error as { status?: unknown }).status;
    return {
      kind: "failed",
      message:
        typeof status === "number" && status > 0
          ? `The server returned an error (${status}).`
          : "The server returned an error.",
    };
  }
  // Anything else carries pdf.js's own wording ("Invalid PDF structure", at
  // times a stack): keep it for the console and show a plain sentence.
  console.error("pdf.js could not open the document", error);
  return { kind: "failed", message: "The document couldn't be opened." };
}

export interface PdfOpening {
  readonly promise: Promise<OpenedPdf>;
  /** Stops the load and frees the document and its worker. Safe to call twice. */
  destroy(): void;
}

/** A document asking for its password, mid-load. */
export interface PasswordPrompt {
  /** The last password given was wrong. */
  readonly incorrect: boolean;
  /** Continues the same load with this password: nothing is downloaded again. */
  submit(password: string): void;
}

export interface PdfOpenOptions {
  /**
   * Called each time the document asks for a password. Without it, a
   * password-protected document fails with pdf.js's `PasswordException`.
   */
  onPassword?: (prompt: PasswordPrompt) => void;
}

// pdf.js PasswordResponses.INCORRECT_PASSWORD.
const INCORRECT_PASSWORD = 2;

/** Opens a document and reads its page sizes. Call `destroy` when done with it. */
export function openPdfDocument(
  source: PdfSource,
  options: PdfOpenOptions = {},
): PdfOpening {
  let task: PDFDocumentLoadingTask | null = null;
  let destroyed = false;
  const promise = (async () => {
    const pdfjs = await loadPdfjs();
    if (destroyed) {
      throw new Error("The document was closed before it opened.");
    }
    task = pdfjs.getDocument(toDocumentParams(source));
    const { onPassword } = options;
    if (onPassword) {
      // pdf.js waits on this callback instead of failing, with the download
      // and the worker kept, so a password costs no second download.
      task.onPassword = (
        update: (password: string) => void,
        reason: number,
      ) => {
        if (destroyed) {
          return;
        }
        onPassword({
          incorrect: reason === INCORRECT_PASSWORD,
          submit(password) {
            if (!destroyed) {
              update(password);
            }
          },
        });
      };
    }
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
      // Destroying the loading task also destroys its document. It rejects
      // when the worker is already gone, which leaves nothing to free.
      task?.destroy().catch(() => undefined);
    },
  };
}
