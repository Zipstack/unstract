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

// Every page/count pair the toolbar is rendered with, to catch a stale one.
const toolbarRenders = vi.hoisted(() => [] as [number, number][]);
vi.mock("./ViewerToolbar", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./ViewerToolbar")>();
  return {
    ...actual,
    ViewerToolbar: (props: Parameters<typeof actual.ViewerToolbar>[0]) => {
      toolbarRenders.push([props.pageIndex, props.pageCount]);
      return actual.ViewerToolbar(props);
    },
  };
});

// The platform's scrollbar, as the viewer would measure it.
const scrollbar = vi.hoisted(() => ({ width: 16 }));
vi.mock("@v1/lib/scrollbar", () => ({
  scrollbarWidth: () => scrollbar.width,
}));

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
  // The body is 864 px wide: 816 + 32 px of padding + a 16 px scrollbar.
  act(() => resize(864, 600));
}

function zoomLabel() {
  return screen.getByLabelText("Zoom level").textContent;
}

beforeEach(() => {
  scrollbar.width = 16;
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

it("shows text line by line, with the switcher but no paging or zoom", () => {
  render(
    <DocumentViewer
      source={{ kind: "text", text: "first\nsecond" }}
      textHighlights={[{ id: "l", line: 1 }]}
      switcher={<button type="button">invoice.pdf</button>}
    />,
  );
  expect(screen.getByRole("region", { name: "Document text" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "invoice.pdf" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Zoom in" })).toBeNull();
  expect(screen.queryByLabelText("Page")).toBeNull();
});

it("keeps the switcher while a PDF is still loading or has failed", async () => {
  render(
    <DocumentViewer
      source={source}
      switcher={<button type="button">invoice.pdf</button>}
    />,
  );
  expect(screen.getByRole("button", { name: "invoice.pdf" })).toBeTruthy();
  await act(async () => opening.reject(new Error("Network error")));
  expect(screen.getByRole("button", { name: "invoice.pdf" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Zoom in" })).toBeNull();
});

it("zooms an image with the toolbar, fitted like a page, without paging", () => {
  render(<DocumentViewer source={{ kind: "image", url: "/scan.png" }} />);
  const image = screen.getByRole<HTMLImageElement>("img", { hidden: true });
  Object.defineProperties(image, {
    naturalWidth: { value: 1632 },
    naturalHeight: { value: 2112 },
  });
  fireEvent.load(image);
  act(() => resize?.(864, 600));
  // 1632 natural px into an 816 px fit: 50%.
  expect(zoomLabel()).toBe("50%");
  expect(screen.queryByLabelText("Page")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
  expect(zoomLabel()).toBe("75%");
});

it("is empty without a source", () => {
  render(<DocumentViewer source={null} />);
  expect(screen.getByText("No document")).toBeTruthy();
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

function loadImage(width: number, height: number) {
  const image = screen.getByRole<HTMLImageElement>("img", { hidden: true });
  Object.defineProperties(image, {
    naturalWidth: { value: width },
    naturalHeight: { value: height },
  });
  fireEvent.load(image);
}

it("leaves paging keys to the browser for text and images", () => {
  const { rerender } = render(
    <DocumentViewer source={{ kind: "text", text: "a\nb" }} />,
  );
  const text = screen.getByRole("region", { name: "Document text" });
  // fireEvent returns false when the handler called preventDefault.
  expect(fireEvent.keyDown(text, { key: "PageDown" })).toBe(true);
  expect(fireEvent.keyDown(text, { key: "End" })).toBe(true);
  expect(fireEvent.keyDown(text, { key: "+" })).toBe(true);

  rerender(<DocumentViewer source={{ kind: "image", url: "/scan.png" }} />);
  loadImage(1632, 2112);
  const image = screen.getByRole("region", { name: "Image viewer" });
  expect(fireEvent.keyDown(image, { key: "PageDown" })).toBe(true);
  expect(fireEvent.keyDown(image, { key: "+" })).toBe(false);
});

it("runs a highlight scroll asked for before an image loads once it has", () => {
  const ref = createRef<DocumentViewerHandle>();
  render(
    <DocumentViewer
      ref={ref}
      source={{ kind: "image", url: "/scan.png" }}
      highlights={[
        {
          id: "h",
          page: 0,
          x: 0.5,
          y: 0.9,
          w: 0.1,
          h: 0.05,
          variant: "box",
          tone: "default",
        },
      ]}
    />,
  );
  const region = screen.getByRole("region", { name: "Image viewer" });
  act(() => ref.current?.scrollToHighlight("h"));
  expect(region.scrollTop).toBe(0);
  const frame = region.querySelector<HTMLElement>("img")?.parentElement;
  if (!frame) {
    throw new Error("no frame");
  }
  Object.defineProperty(frame, "offsetHeight", { value: 1000 });
  Object.defineProperty(region, "clientHeight", { value: 400 });
  loadImage(1632, 2112);
  // Centre of the box at 0.925 of 1000 px, minus half the 400 px viewport.
  expect(region.scrollTop).toBeCloseTo(725);
});

it("draws only page 0's highlights over an image", () => {
  const { container } = render(
    <DocumentViewer
      source={{ kind: "image", url: "/scan.png" }}
      highlights={[
        {
          id: "a",
          page: 0,
          x: 0.1,
          y: 0.1,
          w: 0.1,
          h: 0.1,
          variant: "box",
          tone: "default",
        },
        {
          id: "b",
          page: 1,
          x: 0.1,
          y: 0.1,
          w: 0.1,
          h: 0.1,
          variant: "box",
          tone: "default",
        },
      ]}
    />,
  );
  loadImage(1632, 2112);
  expect(container.querySelector('[data-highlight-id="a"]')).not.toBeNull();
  expect(container.querySelector('[data-highlight-id="b"]')).toBeNull();
});

it("waits for an image to load again after another source was shown", async () => {
  const image = { kind: "image", url: "/scan.png" } as const;
  const { rerender } = render(<DocumentViewer source={image} />);
  loadImage(1632, 2112);
  act(() => resize?.(864, 600));
  expect(screen.queryByRole("button", { name: "Zoom in" })).not.toBeNull();

  rerender(<DocumentViewer source={{ kind: "text", text: "a" }} />);
  rerender(<DocumentViewer source={image} />);
  expect(screen.queryByRole("button", { name: "Zoom in" })).toBeNull();
  loadImage(1632, 2112);
  expect(screen.queryByRole("button", { name: "Zoom in" })).not.toBeNull();
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

it("drops a waiting scroll when the source changes, even back to its own document", async () => {
  const restore = layOutEveryPage();
  try {
    const ref = createRef<DocumentViewerHandle>();
    const other: PdfSource = { kind: "url", url: "/other.pdf" };
    const { rerender } = render(<DocumentViewer ref={ref} source={source} />);
    act(() => ref.current?.scrollToPage(2));
    // Away and back before either document has opened.
    rerender(<DocumentViewer ref={ref} source={other} />);
    rerender(<DocumentViewer ref={ref} source={source} />);
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

it("opens another text at the top, in a fresh view", () => {
  const { rerender } = render(
    <DocumentViewer source={{ kind: "text", text: "first\ntext" }} />,
  );
  const before = screen.getByRole("region", { name: "Document text" });
  before.scrollTop = 300;
  rerender(<DocumentViewer source={{ kind: "text", text: "second\ntext" }} />);
  const after = screen.getByRole("region", { name: "Document text" });
  expect(after).not.toBe(before);
  expect(after.scrollTop).toBe(0);
});

it("drops a scroll waiting on an empty text when another text is shown", () => {
  const original = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "offsetTop",
  );
  Object.defineProperty(HTMLElement.prototype, "offsetTop", {
    configurable: true,
    get(this: HTMLElement) {
      const line = this.getAttribute("data-line");
      return line === null ? 0 : Number(line) * 20;
    },
  });
  try {
    const ref = createRef<DocumentViewerHandle>();
    const { rerender } = render(
      <DocumentViewer ref={ref} source={{ kind: "text", text: "" }} />,
    );
    // An empty text shows a status, not lines, so this has nowhere to go.
    act(() => ref.current?.scrollToHighlight("total"));
    rerender(
      <DocumentViewer
        ref={ref}
        source={{ kind: "text", text: "a\nb\nc\nd\ne\nf" }}
        textHighlights={[{ id: "total", line: 5 }]}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Document text" }).scrollTop,
    ).toBe(0);
  } finally {
    if (original) {
      Object.defineProperty(HTMLElement.prototype, "offsetTop", original);
    }
  }
});

it("does not scroll to an active highlight cleared as it arrives", async () => {
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
    // One render brings the highlight in and clears the selection.
    rerender(
      <DocumentViewer
        source={source}
        highlights={[onPage1]}
        activeHighlightId={null}
      />,
    );
    expect(pagesRegion().scrollTop).toBe(0);
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

it("fits the width to the measured scrollbar, so a 17 px one adds no horizontal scroll", async () => {
  scrollbar.width = 17;
  render(<DocumentViewer source={source} />);
  await open();
  const page = screen.getAllByRole("figure")[0];
  const width = Number.parseFloat(
    page?.style.getPropertyValue("--page-width") ?? "",
  );
  // 864 - 32 - 17 = 815 px for the page, not 816.
  expect(width).toBeCloseTo(815);
});

it("waits for the viewer's size before laying out pages in a fit mode", async () => {
  render(<DocumentViewer source={source} />);
  await act(async () => opening.resolve({ document, pageSizes }));
  expect(screen.getByRole("toolbar")).toBeTruthy();
  expect(screen.queryAllByRole("figure")).toHaveLength(0);
  act(() => resize(864, 600));
  expect(screen.getAllByRole("figure")).toHaveLength(3);
});

it("starts a new document on its first page", async () => {
  const { rerender } = render(<DocumentViewer source={source} />);
  await open();
  fireEvent.keyDown(screen.getByRole("region", { name: "Document pages" }), {
    key: "End",
  });
  expect(screen.getByLabelText("Page")).toHaveProperty("value", "3");

  toolbarRenders.length = 0;
  rerender(<DocumentViewer source={{ kind: "url", url: "/other.pdf" }} />);
  const other = { ...document, numPages: 1 } as PDFDocumentProxy;
  await act(async () =>
    opening.resolve({ document: other, pageSizes: pageSizes.slice(0, 1) }),
  );
  expect(screen.getByLabelText("Page")).toHaveProperty("value", "1");
  expect(screen.getByText("/ 1")).toBeTruthy();
  // Not even one render showed page 3 of 1.
  expect(toolbarRenders.filter(([index, count]) => index >= count)).toEqual([]);
});

it("keeps a live-edited text in place while its id stays the same", () => {
  const { rerender } = render(
    <DocumentViewer
      source={{ kind: "text", id: "doc-1", text: "first\ntext" }}
    />,
  );
  const before = screen.getByRole("region", { name: "Document text" });
  before.scrollTop = 300;
  rerender(
    <DocumentViewer
      source={{ kind: "text", id: "doc-1", text: "first\ntexts" }}
    />,
  );
  const after = screen.getByRole("region", { name: "Document text" });
  expect(after).toBe(before);
  expect(after.scrollTop).toBe(300);
  expect(after.textContent).toContain("texts");

  rerender(
    <DocumentViewer
      source={{ kind: "text", id: "doc-2", text: "first\ntexts" }}
    />,
  );
  expect(screen.getByRole("region", { name: "Document text" })).not.toBe(
    before,
  );
});

it("ignores zoom keys until an image has loaded, so it still opens fitted", () => {
  render(<DocumentViewer source={{ kind: "image", url: "/scan.png" }} />);
  const region = screen.getByRole("region", { name: "Image viewer" });
  // Not handled: fireEvent returns true when nothing called preventDefault.
  expect(fireEvent.keyDown(region, { key: "+" })).toBe(true);
  act(() => resize(864, 600));
  loadImage(1632, 2112);
  expect(
    screen
      .getByRole("button", { name: "Fit width" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

it("drops a scroll to a highlight on another page of an image instead of keeping it", () => {
  const ref = createRef<DocumentViewerHandle>();
  const box = {
    id: "h",
    x: 0.5,
    y: 0.9,
    w: 0.1,
    h: 0.05,
    variant: "box" as const,
    tone: "default" as const,
  };
  const { rerender } = render(
    <DocumentViewer
      ref={ref}
      source={{ kind: "image", url: "/scan.png" }}
      highlights={[{ ...box, page: 1 }]}
    />,
  );
  const region = screen.getByRole("region", { name: "Image viewer" });
  const frame = region.querySelector<HTMLElement>("img")?.parentElement;
  if (!frame) {
    throw new Error("no frame");
  }
  Object.defineProperty(frame, "offsetHeight", { value: 1000 });
  Object.defineProperty(region, "clientHeight", { value: 400 });
  loadImage(1632, 2112);
  act(() => ref.current?.scrollToHighlight("h"));
  // Had the request waited, it would fire here, long after it was asked for.
  rerender(
    <DocumentViewer
      ref={ref}
      source={{ kind: "image", url: "/scan.png" }}
      highlights={[{ ...box, page: 0 }]}
    />,
  );
  expect(region.scrollTop).toBe(0);
});

it("runs a scroll waiting on an empty text once that same text fills in", () => {
  const original = Object.getOwnPropertyDescriptor(
    HTMLElement.prototype,
    "offsetTop",
  );
  Object.defineProperty(HTMLElement.prototype, "offsetTop", {
    configurable: true,
    get(this: HTMLElement) {
      const line = this.getAttribute("data-line");
      return line === null ? 0 : Number(line) * 20;
    },
  });
  try {
    const ref = createRef<DocumentViewerHandle>();
    const textHighlights = [{ id: "total", line: 5 }];
    const { rerender } = render(
      <DocumentViewer
        ref={ref}
        source={{ kind: "text", id: "doc", text: "" }}
        textHighlights={textHighlights}
      />,
    );
    act(() => ref.current?.scrollToHighlight("total"));
    // The same text, by id, fills in; the highlights are unchanged.
    rerender(
      <DocumentViewer
        ref={ref}
        source={{ kind: "text", id: "doc", text: "a\nb\nc\nd\ne\nf" }}
        textHighlights={textHighlights}
      />,
    );
    expect(
      screen.getByRole("region", { name: "Document text" }).scrollTop,
    ).toBe(100);
  } finally {
    if (original) {
      Object.defineProperty(HTMLElement.prototype, "offsetTop", original);
    }
  }
});
