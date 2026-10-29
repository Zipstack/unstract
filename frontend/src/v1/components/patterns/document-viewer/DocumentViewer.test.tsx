import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { OpenedPdf, PdfSource } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { createRef } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentViewer, type DocumentViewerHandle } from "./DocumentViewer";

const opening = vi.hoisted(
  (): {
    resolve: (value: OpenedPdf) => void;
    reject: (error: unknown) => void;
  } => ({ resolve: () => undefined, reject: () => undefined }),
);

vi.mock("@v1/lib/pdf/pdfjs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@v1/lib/pdf/pdfjs")>();
  return {
    ...actual,
    openPdfDocument: () => {
      const promise = new Promise<OpenedPdf>((resolve, reject) => {
        opening.resolve = resolve;
        opening.reject = reject;
      });
      return { promise, destroy: vi.fn() };
    },
  };
});

let resize: ((width: number, height: number) => void) | null = null;

class FakeResizeObserver {
  constructor(callback: (entries: ResizeObserverEntry[]) => void) {
    resize = (width, height) =>
      callback([{ contentRect: { width, height } } as ResizeObserverEntry]);
  }
  observe() {
    // Sizes arrive only when a test calls resize().
  }
  disconnect() {
    // Nothing to release.
  }
}

/** Reports nothing, so no page renders: these tests are about the chrome. */
class FakeIntersectionObserver {
  observe() {
    // Never reports an intersection.
  }
  unobserve() {
    // Nothing to stop.
  }
  disconnect() {
    // Nothing to release.
  }
}

const source: PdfSource = { kind: "url", url: "/invoice.pdf" };
const document = {
  numPages: 3,
  getPage: vi.fn(),
} as unknown as PDFDocumentProxy;
// US Letter: 816 CSS px wide at 100%.
const pageSizes = Array.from({ length: 3 }, () => ({
  width: 612,
  height: 792,
}));

async function open() {
  await act(async () => opening.resolve({ document, pageSizes }));
  // The body is 864 px wide: 816 + the 48 px fit gutter.
  act(() => resize?.(864, 600));
}

function zoomLabel() {
  return screen.getByLabelText("Zoom level").textContent;
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});
afterEach(() => vi.unstubAllGlobals());

it("shows the loading state, then the toolbar once the document opens", async () => {
  render(<DocumentViewer source={source} />);
  expect(screen.getByRole("status")).toBeTruthy();
  expect(screen.queryByRole("toolbar")).toBeNull();
  await open();
  expect(screen.getByRole("toolbar")).toBeTruthy();
  expect(screen.getByText("/ 3")).toBeTruthy();
});

it("shows a failure with Retry", async () => {
  render(<DocumentViewer source={source} />);
  await act(async () => opening.reject(new Error("Network error")));
  expect(screen.getByRole("alert").textContent).toContain("Network error");
  expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
});

it("fits the width by default, and zooms in steps from there", async () => {
  render(<DocumentViewer source={source} />);
  await open();
  expect(zoomLabel()).toBe("100%");
  expect(
    screen
      .getByRole("button", { name: "Fit width" })
      .getAttribute("aria-pressed"),
  ).toBe("true");

  await userEvent.click(screen.getByRole("button", { name: "Zoom in" }));
  expect(zoomLabel()).toBe("125%");
  expect(
    screen
      .getByRole("button", { name: "Fit width" })
      .getAttribute("aria-pressed"),
  ).toBe("false");
});

it("refits when the viewer is resized", async () => {
  render(<DocumentViewer source={source} />);
  await open();
  act(() => resize?.(456, 600));
  expect(zoomLabel()).toBe("50%");
});

it("zooms with + and − while the pages have focus, and leaves other keys alone", async () => {
  render(<DocumentViewer source={source} initialZoom={1} />);
  await open();
  const pages = screen.getByRole("region", { name: "Document pages" });
  fireEvent.keyDown(pages, { key: "+" });
  expect(zoomLabel()).toBe("125%");
  fireEvent.keyDown(pages, { key: "-" });
  fireEvent.keyDown(pages, { key: "-" });
  expect(zoomLabel()).toBe("75%");
  fireEvent.keyDown(pages, { key: "+", ctrlKey: true });
  expect(zoomLabel()).toBe("75%");
});

/** Pages 1000 px tall, 16 px apart, as a browser would lay them out. */
function layOutPages() {
  for (const page of window.document.querySelectorAll<HTMLElement>(
    "[data-page-index]",
  )) {
    const index = Number(page.getAttribute("data-page-index"));
    Object.defineProperties(page, {
      offsetTop: { value: 16 + index * 1016 },
      offsetHeight: { value: 1000 },
    });
  }
  return screen.getByRole("region", { name: "Document pages" });
}

it("pages with End and Home while the pages have focus", async () => {
  render(<DocumentViewer source={source} />);
  await open();
  const pages = layOutPages();
  fireEvent.keyDown(pages, { key: "End" });
  expect(pages.scrollTop).toBe(2 * 1016);
  fireEvent.keyDown(pages, { key: "Home" });
  expect(pages.scrollTop).toBe(0);
});

it("runs a scroll asked for while loading once the pages are laid out", async () => {
  // Every page element reports its browser layout from the moment it mounts.
  const original = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "offsetTop",
  );
  Object.defineProperty(HTMLElement.prototype, "offsetTop", {
    configurable: true,
    get(this: HTMLElement) {
      const index = this.getAttribute("data-page-index");
      return index === null ? 0 : 16 + Number(index) * 1016;
    },
  });
  try {
    const ref = createRef<DocumentViewerHandle>();
    render(<DocumentViewer ref={ref} source={source} />);
    act(() => ref.current?.scrollToPage(2));
    await open();
    expect(
      screen.getByRole("region", { name: "Document pages" }).scrollTop,
    ).toBe(2 * 1016);
  } finally {
    if (original) {
      Object.defineProperty(HTMLElement.prototype, "offsetTop", original);
    }
  }
});
