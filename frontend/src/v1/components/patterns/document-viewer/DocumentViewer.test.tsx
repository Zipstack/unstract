import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { OpenedPdf, PdfSource } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { createRef, useLayoutEffect, useRef } from "react";
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

const resizeCallbacks = new Set<(entries: ResizeObserverEntry[]) => void>();
// Every observer hears the size: the viewer's body and the page list's own.
const resize = (width: number, height: number) => {
  for (const callback of resizeCallbacks) {
    callback([{ contentRect: { width, height } } as ResizeObserverEntry]);
  }
};

class FakeResizeObserver {
  constructor(
    private readonly callback: (entries: ResizeObserverEntry[]) => void,
  ) {}
  observe() {
    // Sizes arrive only when a test calls resize().
    resizeCallbacks.add(this.callback);
  }
  disconnect() {
    resizeCallbacks.delete(this.callback);
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
  act(() => resize(864, 600));
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

it("shows a failure with Retry, in plain words rather than pdf.js's", async () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
  render(<DocumentViewer source={source} />);
  await act(async () => opening.reject(new Error("Network error")));
  log.mockRestore();
  const alert = screen.getByRole("alert").textContent;
  expect(alert).toContain("The document couldn't be opened.");
  expect(alert).not.toContain("Network error");
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
  act(() => resize(456, 600));
  expect(zoomLabel()).toBe("50%");
});

it.each([
  [0, "25%"],
  [Number.NaN, "100%"],
  [10, "400%"],
])("keeps a starting zoom of %s within range", async (initialZoom, label) => {
  render(<DocumentViewer source={source} initialZoom={initialZoom} />);
  await open();
  expect(zoomLabel()).toBe(label);
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

it("fits every page in fit page, so a wider page later on sets the zoom", async () => {
  render(<DocumentViewer source={source} />);
  await act(async () =>
    opening.resolve({
      document,
      // A portrait page first, then a landscape one.
      pageSizes: [
        { width: 612, height: 792 },
        { width: 792, height: 612 },
      ],
    }),
  );
  // Tall enough that only width limits: 816 px across, after the gutter.
  act(() => resize(864, 2000));
  await userEvent.click(screen.getByRole("button", { name: "Fit page" }));
  // The landscape page is 1056 px wide at 100%: 816 / 1056 ≈ 77%.
  expect(zoomLabel()).toBe("77%");
});

it("pages forward and back with PageDown and PageUp, one page per press", async () => {
  render(<DocumentViewer source={source} />);
  await open();
  const pages = layOutPages();
  fireEvent.keyDown(pages, { key: "PageDown" });
  fireEvent.keyDown(pages, { key: "PageDown" });
  expect(pages.scrollTop).toBe(2 * 1016);
  expect(screen.getByLabelText<HTMLInputElement>("Page").value).toBe("3");
  fireEvent.keyDown(pages, { key: "PageUp" });
  expect(pages.scrollTop).toBe(1016);
  expect(screen.getByLabelText<HTMLInputElement>("Page").value).toBe("2");
});

/**
 * Lays out every page element from the moment it mounts: 1000 px tall, 16 px
 * apart. Returns a function that puts the prototype back.
 */
function layOutEveryPage() {
  const originals = (["offsetTop", "offsetHeight"] as const).map(
    (name) =>
      [
        name,
        Object.getOwnPropertyDescriptor(HTMLElement.prototype, name),
      ] as const,
  );
  Object.defineProperties(HTMLElement.prototype, {
    offsetTop: {
      configurable: true,
      get(this: HTMLElement) {
        const index = this.getAttribute("data-page-index");
        return index === null ? 0 : 16 + Number(index) * 1016;
      },
    },
    offsetHeight: {
      configurable: true,
      get(this: HTMLElement) {
        return this.hasAttribute("data-page-index") ? 1000 : 0;
      },
    },
  });
  return () => {
    for (const [name, descriptor] of originals) {
      if (descriptor) {
        Object.defineProperty(HTMLElement.prototype, name, descriptor);
      }
    }
  };
}

const onPage1 = {
  id: "total",
  page: 1,
  x: 0.1,
  y: 0.5,
  w: 0.2,
  h: 0,
  variant: "box" as const,
  tone: "default" as const,
};
// Page 1's top is at 1032, padding included, and the highlight's centre is
// 500 px into it; the viewer reports no height, so centring adds nothing.
const onPage1Top = 1032 + 500;

function pagesRegion() {
  return screen.getByRole("region", { name: "Document pages" });
}

it("drops a scroll asked for one document when another is shown", async () => {
  const restore = layOutEveryPage();
  try {
    const ref = createRef<DocumentViewerHandle>();
    const { rerender } = render(<DocumentViewer ref={ref} source={source} />);
    act(() => ref.current?.scrollToPage(2));
    rerender(
      <DocumentViewer ref={ref} source={{ kind: "url", url: "/other.pdf" }} />,
    );
    await open();
    expect(pagesRegion().scrollTop).toBe(0);
  } finally {
    restore();
  }
});

it("scrolls to the active highlight when it changes, and to one set while loading", async () => {
  const restore = layOutEveryPage();
  try {
    const { rerender } = render(
      <DocumentViewer
        source={source}
        highlights={[onPage1]}
        activeHighlightId="total"
      />,
    );
    await open();
    expect(pagesRegion().scrollTop).toBe(onPage1Top);

    pagesRegion().scrollTop = 0;
    rerender(
      <DocumentViewer
        source={source}
        highlights={[onPage1, { ...onPage1, id: "date", page: 2 }]}
        activeHighlightId="date"
      />,
    );
    expect(pagesRegion().scrollTop).toBe(16 + 2 * 1016 + 500);
  } finally {
    restore();
  }
});

it("scrolls to an active highlight that arrives after its id", async () => {
  const restore = layOutEveryPage();
  try {
    const { rerender } = render(
      <DocumentViewer
        source={source}
        highlights={[]}
        activeHighlightId="total"
      />,
    );
    await open();
    expect(pagesRegion().scrollTop).toBe(0);
    rerender(
      <DocumentViewer
        source={source}
        highlights={[onPage1]}
        activeHighlightId="total"
      />,
    );
    expect(pagesRegion().scrollTop).toBe(onPage1Top);
  } finally {
    restore();
  }
});

it("keeps a scroll a parent asks for in its layout effect on mount", async () => {
  const restore = layOutEveryPage();
  function Parent() {
    const ref = useRef<DocumentViewerHandle>(null);
    useLayoutEffect(() => {
      ref.current?.scrollToPage(2);
    }, []);
    return <DocumentViewer ref={ref} source={source} />;
  }
  try {
    render(<Parent />);
    await open();
    expect(pagesRegion().scrollTop).toBe(2 * 1016);
  } finally {
    restore();
  }
});

it("scrolls to an active highlight chosen before its document is shown", async () => {
  const restore = layOutEveryPage();
  try {
    const { rerender } = render(
      <DocumentViewer
        source={source}
        highlights={[]}
        activeHighlightId="total"
      />,
    );
    await open();
    rerender(
      <DocumentViewer
        source={{ kind: "url", url: "/other.pdf" }}
        highlights={[onPage1]}
        activeHighlightId="total"
      />,
    );
    await open();
    expect(pagesRegion().scrollTop).toBe(onPage1Top);
  } finally {
    restore();
  }
});
