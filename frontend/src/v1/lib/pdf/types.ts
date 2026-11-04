import type { PDFDocumentProxy } from "pdfjs-dist";

/** Where a document comes from: fetched by pdf.js, or bytes already in memory. */
export type PdfSource =
  | {
      kind: "url";
      url: string;
      withCredentials?: boolean;
      httpHeaders?: Readonly<Record<string, string>>;
    }
  | { kind: "data"; data: Uint8Array | ArrayBuffer };

/** A page's size in PDF points at scale 1, with the page's own rotation applied. */
export interface PageSize {
  readonly width: number;
  readonly height: number;
}

export interface OpenedPdf {
  readonly document: PDFDocumentProxy;
  /** One entry per page, in page order. */
  readonly pageSizes: readonly PageSize[];
}

/** Why a document could not be opened, in the terms the viewer shows. */
export type PdfLoadFailure =
  | { kind: "password"; incorrect: boolean }
  | { kind: "unsupported" }
  | { kind: "failed"; message: string };
