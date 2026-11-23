import type { Highlight } from "@v1/lib/pdf/highlights";
import type { DocumentSource } from "@v1/lib/pdf/types";
import type { ReactElement } from "react";
import { DocumentViewer } from "./DocumentViewer";
import {
  GALLERY_IDS,
  LONG_PDF_PAGES,
  MARK_RGB,
  TARGETS,
} from "./gallery.targets";
import { samplePdf } from "./samplePdf";
import type { TextLineHighlight } from "./TextView";
import { ViewerStatus, type ViewerStatusState } from "./ViewerStatus";
import { ViewerToolbar, type ViewerToolbarProps } from "./ViewerToolbar";

/*
 * Every view and state of the document viewer, for the component gallery
 * (P1-T01, not merged yet: register these there, where each entry is shown in
 * Light, Dark and Unstract). Until then the development-only demo page
 * `/:orgName/v1-demo-viewer` shows them all, and the browser tests
 * (tests/e2e/ui-v1/specs/P1-T21.spec.ts) run on it. markup.test.tsx snapshots
 * the markup of every entry that renders without a real browser; the PDF
 * entries need pdf.js and a canvas, so only the browser tests cover them.
 */

export type GalleryEntry = Readonly<{
  /** Stable id: the demo page's test id is VIEWER_GALLERY_TEST_ID_PREFIX + id. */
  id: string;
  name: string;
  element: ReactElement;
  /** Needs pdf.js and a canvas, so it renders only in a real browser. */
  browserOnly?: boolean;
}>;

const noop = (): void => undefined;

/** The viewer's box in the gallery: tall enough to scroll, fixed so it does. */
const VIEWER_CLASS = "ui:h-128 ui:rounded-md ui:border ui:border-border";

/** The target highlights: each sits on a mark drawn at the same fractions. */
const TARGET_HIGHLIGHTS: readonly Highlight[] = TARGETS.map((target) => ({
  ...target,
  page: 0,
  tone: "default",
}));

const SAMPLE_HIGHLIGHTS: readonly Highlight[] = [
  {
    id: "sample-line",
    page: 0,
    x: 0.1,
    y: 0.2,
    w: 0.8,
    h: 0.025,
    variant: "line",
    tone: "default",
    confidence: 0.97,
  },
  {
    id: "sample-low",
    page: 0,
    x: 0.1,
    y: 0.26,
    w: 0.8,
    h: 0.025,
    variant: "line",
    tone: "low-confidence",
    confidence: 0.62,
  },
  {
    id: "sample-box",
    page: 0,
    x: 0.55,
    y: 0.4,
    w: 0.3,
    h: 0.08,
    variant: "box",
    tone: "default",
  },
  {
    id: "sample-active",
    page: 1,
    x: 0.1,
    y: 0.3,
    w: 0.5,
    h: 0.04,
    variant: "box",
    tone: "default",
  },
];

/*
 * Built on first use, not when the module loads: the 200-page PDF is a few
 * hundred kilobytes of string work that only the demo page needs.
 */
function pdf(build: () => Uint8Array): DocumentSource {
  let data: Uint8Array | undefined;
  return {
    kind: "data",
    get data() {
      data ??= build();
      return data;
    },
  };
}

const SAMPLE_PDF = pdf(() => samplePdf({ pages: 3 }));
const LONG_PDF = pdf(() => samplePdf({ pages: LONG_PDF_PAGES }));
const TARGET_PDF = pdf(() =>
  samplePdf({
    pages: 1,
    marks: (index) =>
      index === 0
        ? TARGETS.map((target) => ({ ...target, rgb: MARK_RGB }))
        : [],
  }),
);

/** Not a PDF: pdf.js refuses it, so the viewer shows "can't be previewed". */
const NOT_A_PDF: DocumentSource = {
  kind: "data",
  data: new TextEncoder().encode("plain text, not a PDF"),
};

/**
 * A 400 × 300 image, as an inline SVG: two blocks, the lower one where its
 * highlight sits. Default fills only, as v1 source holds no raw colours.
 */
const IMAGE: DocumentSource = {
  kind: "image",
  alt: "Sample scanned receipt",
  url: `data:image/svg+xml,${encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect x="40" y="20" width="120" height="24"/><rect x="40" y="60" width="200" height="30" fill-opacity="0.2"/></svg>',
  )}`,
};

const IMAGE_HIGHLIGHTS: readonly Highlight[] = [
  {
    id: "image-box",
    page: 0,
    x: 0.1,
    y: 0.2,
    w: 0.5,
    h: 0.1,
    variant: "box",
    tone: "low-confidence",
    confidence: 0.71,
  },
];

const TEXT: DocumentSource = {
  kind: "text",
  id: "gallery-text",
  text: Array.from(
    { length: 40 },
    (_, index) => `Line ${index + 1}: extracted text from the document`,
  ).join("\n"),
};

const TEXT_HIGHLIGHTS: readonly TextLineHighlight[] = [
  { id: "text-line", line: 2 },
  { id: "text-low", line: 5, tone: "low-confidence" },
  { id: "text-active", line: 8 },
];

function viewer(props: Parameters<typeof DocumentViewer>[0]): ReactElement {
  return <DocumentViewer className={VIEWER_CLASS} {...props} />;
}

const TOOLBAR_BASE: ViewerToolbarProps = {
  pageIndex: 0,
  pageCount: 12,
  zoom: 1,
  zoomMode: "custom",
  canZoomIn: true,
  canZoomOut: true,
  onPageChange: noop,
  onZoomIn: noop,
  onZoomOut: noop,
  onFitWidth: noop,
  onFitPage: noop,
};

function toolbar(props: Partial<ViewerToolbarProps>): ReactElement {
  return <ViewerToolbar {...TOOLBAR_BASE} {...props} />;
}

function status(state: ViewerStatusState): ReactElement {
  return <ViewerStatus state={state} onRetry={noop} onSubmitPassword={noop} />;
}

export const VIEWER_GALLERY: readonly GalleryEntry[] = [
  {
    id: "pdf-highlights",
    name: "PDF: highlights in every tone, one active",
    browserOnly: true,
    element: viewer({
      source: SAMPLE_PDF,
      highlights: SAMPLE_HIGHLIGHTS,
      activeHighlightId: "sample-active",
      onHighlightClick: noop,
    }),
  },
  {
    id: GALLERY_IDS.long,
    name: `PDF: ${LONG_PDF_PAGES} pages`,
    browserOnly: true,
    element: viewer({ source: LONG_PDF }),
  },
  {
    id: GALLERY_IDS.targets,
    name: "PDF: highlights on known marks, at 100%",
    browserOnly: true,
    element: viewer({
      source: TARGET_PDF,
      highlights: TARGET_HIGHLIGHTS,
      initialZoom: 1,
    }),
  },
  {
    id: "pdf-unsupported",
    name: "PDF: not a PDF",
    browserOnly: true,
    element: viewer({ source: NOT_A_PDF }),
  },
  {
    id: "image",
    name: "Image: with a low-confidence highlight",
    element: viewer({
      source: IMAGE,
      highlights: IMAGE_HIGHLIGHTS,
      onHighlightClick: noop,
    }),
  },
  {
    id: "text",
    name: "Text: line highlights, one active",
    element: viewer({
      source: TEXT,
      textHighlights: TEXT_HIGHLIGHTS,
      activeHighlightId: "text-active",
      onTextHighlightClick: noop,
    }),
  },
  {
    id: "text-empty",
    name: "Text: nothing extracted",
    element: viewer({ source: { kind: "text", text: "" } }),
  },
  {
    id: "no-document",
    name: "No document",
    element: viewer({ source: null }),
  },
  {
    id: "toolbar-first-page",
    name: "Toolbar: first page, fit width",
    element: toolbar({ zoomMode: "fit-width", zoom: 1.1 }),
  },
  {
    id: "toolbar-last-page",
    name: "Toolbar: last page, largest zoom",
    element: toolbar({ pageIndex: 11, zoom: 4, canZoomIn: false }),
  },
  {
    id: "toolbar-smallest-zoom",
    name: "Toolbar: smallest zoom, fit page",
    element: toolbar({
      pageIndex: 4,
      zoom: 0.25,
      zoomMode: "fit-page",
      canZoomOut: false,
    }),
  },
  {
    id: "toolbar-image",
    name: "Toolbar: image (no paging), with a switcher",
    element: toolbar({
      pageCount: 1,
      showPaging: false,
      leading: <span className="ui:text-body-small">Document</span>,
    }),
  },
  {
    id: "toolbar-text",
    name: "Toolbar: text (no zoom)",
    element: toolbar({ pageCount: 1, showPaging: false, showZoom: false }),
  },
  {
    id: "status-loading",
    name: "Status: loading",
    element: status({ status: "loading" }),
  },
  {
    id: "status-empty",
    name: "Status: no document",
    element: status({ status: "empty" }),
  },
  {
    id: "status-no-text",
    name: "Status: no text",
    element: status({ status: "no-text" }),
  },
  {
    id: "status-unsupported",
    name: "Status: unsupported file",
    element: status({ status: "unsupported" }),
  },
  {
    id: "status-failed",
    name: "Status: failed to load",
    element: status({ status: "failed", message: "Network error" }),
  },
  {
    id: "status-password",
    name: "Status: password needed",
    element: status({ status: "password", incorrect: false }),
  },
  {
    id: "status-password-incorrect",
    name: "Status: password incorrect",
    element: status({ status: "password", incorrect: true }),
  },
];
