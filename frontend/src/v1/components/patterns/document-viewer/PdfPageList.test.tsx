import { act, render } from "@testing-library/react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { createRef } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PdfPageList, type PdfPageListHandle } from "./PdfPageList";

/** An IntersectionObserver whose "in view" set the test controls. */
class FakeIntersectionObserver {
  static current: FakeIntersectionObserver | null = null;
  readonly targets = new Set<Element>();
  constructor(
    private readonly callback: (entries: IntersectionObserverEntry[]) => void,
  ) {
    FakeIntersectionObserver.current = this;
  }
  observe(target: Element) {
    this.targets.add(target);
  }
  unobserve(target: Element) {
    this.targets.delete(target);
  }
  disconnect() {
    this.targets.clear();
  }
  emit(entries: object[]) {
    this.callback(entries as unknown as IntersectionObserverEntry[]);
  }
  show(indexes: number[]) {
    const entries = [...this.targets].map((target) => ({
      target,
      isIntersecting: indexes.includes(
        Number(target.getAttribute("data-page-index")),
      ),
      intersectionRatio: indexes.includes(
        Number(target.getAttribute("data-page-index")),
      )
        ? 1
        : 0,
    }));
    this.callback(entries as unknown as IntersectionObserverEntry[]);
  }
}

interface FakeTask {
  promise: Promise<void>;
  cancel: ReturnType<typeof vi.fn>;
  finish: () => void;
  fail: (error: unknown) => void;
}

function fakeDocument(pageCount: number) {
  const tasks: FakeTask[] = [];
  const pages = new Map<number, { cleanup: ReturnType<typeof vi.fn> }>();
  const render = vi.fn(() => {
    let finish!: () => void;
    let fail!: (error: unknown) => void;
    const promise = new Promise<void>((resolve, reject) => {
      finish = resolve;
      fail = reject;
    });
    const task: FakeTask = {
      promise,
      finish,
      fail,
      cancel: vi.fn(() =>
        fail(
          Object.assign(new Error("cancelled"), {
            name: "RenderingCancelledException",
          }),
        ),
      ),
    };
    tasks.push(task);
    return task;
  });
  const document = {
    numPages: pageCount,
    getPage: vi.fn(async (n: number) => {
      const page = {
        getViewport: ({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        }),
        render,
        cleanup: vi.fn(),
      };
      pages.set(n, page);
      return page;
    }),
  } as unknown as PDFDocumentProxy;
  return { document, render, tasks, pages };
}

const sizes = (count: number) =>
  Array.from({ length: count }, () => ({ width: 600, height: 800 }));

async function flush() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

function show(indexes: number[]) {
  act(() => FakeIntersectionObserver.current?.show(indexes));
}

let viewerResized: (() => void) | null = null;

class FakeResizeObserver {
  constructor(callback: () => void) {
    viewerResized = callback;
  }
  observe() {
    // Reports only when a test calls viewerResized().
  }
  disconnect() {
    viewerResized = null;
  }
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) =>
    window.setTimeout(() => cb(0), 0),
  );
  vi.stubGlobal("cancelAnimationFrame", (id: number) =>
    window.clearTimeout(id),
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: vi.fn(),
  } as unknown as CanvasRenderingContext2D);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  window.devicePixelRatio = 1;
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("lays out every page at its own size before rendering any", () => {
  const { document } = fakeDocument(3);
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={[
        { width: 600, height: 800 },
        { width: 800, height: 600 },
        { width: 600, height: 800 },
      ]}
      zoom={1}
    />,
  );
  const pages = container.querySelectorAll<HTMLElement>("[data-page-index]");
  expect(pages).toHaveLength(3);
  expect(
    Number.parseFloat(pages[1]?.style.getPropertyValue("--page-width") ?? ""),
  ).toBeCloseTo(800 * (96 / 72));
  expect(pages[1]?.style.getPropertyValue("--page-height")).toBe("800px");
  expect(pages[1]?.getAttribute("aria-label")).toBe("Page 2 of 3");
  expect(container.querySelectorAll("canvas")).toHaveLength(0);
});

it("keeps the live canvas count bounded while scrolling 200 pages end to end", async () => {
  const { document } = fakeDocument(200);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(200)} zoom={1} />,
  );
  let most = 0;
  for (let first = 0; first < 200; first += 2) {
    show([first, first + 1]);
    most = Math.max(most, container.querySelectorAll("canvas").length);
  }
  // Two visible pages plus two on each side.
  expect(most).toBeLessThanOrEqual(6);
  const live = [...container.querySelectorAll("canvas")].map((canvas) =>
    Number(canvas.parentElement?.getAttribute("data-page-index")),
  );
  expect(live).toEqual([196, 197, 198, 199]);
});

it("renders at the screen's pixel ratio, capped at 2", async () => {
  window.devicePixelRatio = 3;
  const { document, render: renderPage, tasks } = fakeDocument(1);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(1)} zoom={1} />,
  );
  show([0]);
  await flush();
  await act(async () => tasks[0]?.finish());
  const canvas = container.querySelector("canvas");
  expect(renderPage).toHaveBeenCalledTimes(1);
  const [params] = renderPage.mock.calls[0] as unknown as [
    { transform?: number[]; viewport: { width: number } },
  ];
  expect(params.transform).toEqual([2, 0, 0, 2, 0, 0]);
  expect(canvas?.width).toBe(Math.floor(params.viewport.width * 2));
});

it("cancels the render in flight when the zoom changes", async () => {
  const { document, tasks } = fakeDocument(1);
  const { rerender } = render(
    <PdfPageList document={document} pageSizes={sizes(1)} zoom={1} />,
  );
  show([0]);
  await flush();
  expect(tasks).toHaveLength(1);

  rerender(<PdfPageList document={document} pageSizes={sizes(1)} zoom={2} />);
  await flush();
  expect(tasks[0]?.cancel).toHaveBeenCalledTimes(1);
  expect(tasks).toHaveLength(2);
});

it("keeps the last picture up while a zoom change draws the new one", async () => {
  const { document, tasks } = fakeDocument(1);
  const { container, rerender } = render(
    <PdfPageList document={document} pageSizes={sizes(1)} zoom={1} />,
  );
  show([0]);
  await flush();
  await act(async () => tasks[0]?.finish());
  const canvas = container.querySelector("canvas");
  const drawn = canvas?.width;
  expect(drawn).toBeGreaterThan(0);

  rerender(<PdfPageList document={document} pageSizes={sizes(1)} zoom={2} />);
  await flush();
  // The new render is in flight: the old picture is still there.
  expect(container.querySelector("canvas")).toBe(canvas);
  expect(canvas?.width).toBe(drawn);
  await act(async () => tasks[1]?.finish());
  expect(canvas?.width).toBe((drawn ?? 0) * 2);
  expect(renderState(container, 0)).toBe("rendered");
});

it("says a page is rendering from the moment it asks for the page", async () => {
  const { document } = fakeDocument(1);
  (document.getPage as ReturnType<typeof vi.fn>).mockImplementationOnce(
    () => new Promise(() => undefined),
  );
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(1)} zoom={1} />,
  );
  expect(renderState(container, 0)).toBe("idle");
  show([0]);
  await flush();
  expect(renderState(container, 0)).toBe("rendering");
});

it("logs a page that fails to render, with its page number", async () => {
  const { document, tasks } = fakeDocument(3);
  render(<PdfPageList document={document} pageSizes={sizes(3)} zoom={1} />);
  show([0]);
  await flush();
  const failure = new Error("bad page");
  await act(async () => tasks[0]?.fail(failure));
  expect(console.error).toHaveBeenCalledWith("Page 1 didn't render", failure);
});

it("renders each page only once when the window moves", async () => {
  const { document } = fakeDocument(10);
  const overlay = vi.fn((_index: number) => null);
  render(
    <PdfPageList
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      renderPageOverlay={overlay}
    />,
  );
  overlay.mockClear();
  show([5]);
  // Pages 3 to 7 enter the window; the other five pages are not re-rendered.
  expect(new Set(overlay.mock.calls.map(([index]) => index))).toEqual(
    new Set([3, 4, 5, 6, 7]),
  );
});

it("frees the canvas and the page when a page leaves the window", async () => {
  const { document, tasks, pages } = fakeDocument(10);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(10)} zoom={1} />,
  );
  show([0]);
  await flush();
  const canvas = container.querySelector<HTMLCanvasElement>(
    '[data-page-index="0"] canvas',
  );
  await act(async () => tasks[0]?.finish());
  expect(
    container
      .querySelector('[data-page-index="0"]')
      ?.getAttribute("data-render-state"),
  ).toBe("rendered");

  show([9]);
  expect(container.querySelector('[data-page-index="0"] canvas')).toBeNull();
  expect(canvas?.width).toBe(0);
  expect(canvas?.height).toBe(0);
  expect(pages.get(1)?.cleanup).toHaveBeenCalled();
});

function renderState(container: HTMLElement, index: number) {
  return container
    .querySelector(`[data-page-index="${index}"]`)
    ?.getAttribute("data-render-state");
}

it("marks a page whose render fails as an error, not as still rendering", async () => {
  const { document, tasks } = fakeDocument(3);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(3)} zoom={1} />,
  );
  show([0]);
  await flush();
  expect(renderState(container, 0)).toBe("rendering");
  await act(async () => tasks[0]?.fail(new Error("bad page")));
  expect(renderState(container, 0)).toBe("error");
});

it("says a page failed and renders it again on Retry", async () => {
  const { document, tasks } = fakeDocument(3);
  const { container, getByRole } = render(
    <PdfPageList document={document} pageSizes={sizes(3)} zoom={1} />,
  );
  show([0]);
  await flush();
  await act(async () => tasks[0]?.fail(new Error("bad page")));
  expect(container.textContent).toContain("This page didn't load.");
  act(() => getByRole("button", { name: "Retry page 1" }).click());
  await flush();
  expect(renderState(container, 0)).toBe("rendering");
  await act(async () => tasks.at(-1)?.finish());
  expect(renderState(container, 0)).toBe("rendered");
  expect(container.textContent).not.toContain("This page didn't load.");
});

it("marks a page as an error when the canvas has no 2D context", async () => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const { document } = fakeDocument(3);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(3)} zoom={1} />,
  );
  show([0]);
  await flush();
  expect(renderState(container, 0)).toBe("error");
});

it("draws nothing for a page that leaves before its frame comes", async () => {
  const { document, render: renderPage } = fakeDocument(10);
  render(<PdfPageList document={document} pageSizes={sizes(10)} zoom={1} />);
  show([0]);
  show([9]);
  await flush();
  const drawn = new Set(
    (document.getPage as ReturnType<typeof vi.fn>).mock.calls.map(([n]) => n),
  );
  expect(drawn.has(1)).toBe(false);
  expect(renderPage.mock.calls.length).toBeLessThanOrEqual(3);
});

it("draws each highlight on its own page", () => {
  const { document } = fakeDocument(3);
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(3)}
      zoom={1}
      highlights={[
        {
          id: "a",
          page: 2,
          x: 0,
          y: 0.1,
          w: 1,
          h: 0.02,
          variant: "line",
          tone: "default",
        },
        {
          id: "b",
          page: 0,
          x: 0,
          y: 0.5,
          w: 1,
          h: 0.02,
          variant: "line",
          tone: "default",
        },
      ]}
    />,
  );
  expect(
    container.querySelector('[data-page-index="2"] [data-highlight-id="a"]'),
  ).not.toBeNull();
  expect(
    container.querySelector('[data-page-index="0"] [data-highlight-id="b"]'),
  ).not.toBeNull();
  expect(
    container.querySelector('[data-page-index="1"] [data-highlight-id]'),
  ).toBeNull();
});

/**
 * Gives the list a layout, which happy-dom does not compute: pages 800 × 600
 * at zoom 1, 16 px apart after 16 px of padding, in a viewport 500 wide and
 * 400 tall unless `viewHeight` says otherwise.
 */
function layOut(
  container: HTMLElement,
  zoom: () => number,
  viewHeight: () => number = () => 400,
  viewWidth = 500,
) {
  const root = container.querySelector<HTMLElement>("section");
  if (!root) {
    throw new Error("no scroll region");
  }
  const count = container.querySelectorAll("[data-page-index]").length;
  Object.defineProperties(root, {
    clientHeight: { get: viewHeight },
    clientWidth: { value: viewWidth },
    scrollHeight: {
      get: () => 16 + count * (800 * zoom() + 16),
      configurable: true,
    },
  });
  for (const page of container.querySelectorAll<HTMLElement>(
    "[data-page-index]",
  )) {
    const index = Number(page.getAttribute("data-page-index"));
    Object.defineProperties(page, {
      offsetTop: {
        get: () => 16 + index * (800 * zoom() + 16),
        configurable: true,
      },
      offsetHeight: { get: () => 800 * zoom(), configurable: true },
      offsetWidth: { get: () => 600 * zoom() },
      // Centred while narrower than the view, else after the 16 px gutter.
      offsetLeft: { get: () => Math.max(16, (viewWidth - 600 * zoom()) / 2) },
    });
  }
  return root;
}

it("scrolls a page to the top exactly, with no wait", () => {
  const { document } = fakeDocument(10);
  const ref = createRef<PdfPageListHandle>();
  const { container } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
    />,
  );
  const root = layOut(container, () => 1);
  act(() => ref.current?.scrollToPage(3));
  expect(root.scrollTop).toBe(3 * 816);
  act(() => ref.current?.scrollToPage(99));
  expect(root.scrollTop).toBe(9 * 816);
});

it("centres a highlight, across as well as down for a box", () => {
  const { document } = fakeDocument(10);
  const ref = createRef<PdfPageListHandle>();
  const highlights = [
    {
      id: "w",
      page: 2,
      x: 0.5,
      y: 0.25,
      w: 0.1,
      h: 0.05,
      variant: "box" as const,
      tone: "default" as const,
    },
  ];
  const { container } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      highlights={highlights}
    />,
  );
  const root = layOut(container, () => 1);
  let found = false;
  act(() => {
    found = ref.current?.scrollToHighlight("w") ?? false;
  });
  expect(found).toBe(true);
  // Page 2's top is at 1648, padding included; the box's centre is
  // 0.275 × 800 = 220 into it, and the view is 400 tall.
  expect(root.scrollTop).toBe(1648 + 220 - 200);
  // 0.55 × 600 = 330 across, from the page's left edge at 16.
  expect(root.scrollLeft).toBe(16 + 330 - 250);
  expect(ref.current?.scrollToHighlight("missing")).toBe(false);
});

/** Scrolls at zoom 1 with `place`, then zooms to 2; returns the scroller. */
function zoomInAfter(
  place: (root: HTMLElement) => void,
  viewWidth?: number,
): HTMLElement {
  const { document } = fakeDocument(10);
  let zoom = 1;
  const { container, rerender } = render(
    <PdfPageList document={document} pageSizes={sizes(10)} zoom={zoom} />,
  );
  const root = layOut(container, () => zoom, undefined, viewWidth);
  place(root);
  act(() => {
    root.dispatchEvent(new Event("scroll"));
  });
  zoom = 2;
  rerender(
    <PdfPageList document={document} pageSizes={sizes(10)} zoom={zoom} />,
  );
  return root;
}

it("keeps the same spot of the same page in view across a zoom change", () => {
  const root = zoomInAfter((scroller) => {
    show([0]);
    // Half way down page 0.
    scroller.scrollTop = 400;
  });
  expect(root.scrollTop).toBe(800);
});

it("keeps the same spot across the page in view across a zoom change", () => {
  // The middle of the 500 px view is 434 px into the 600 px page.
  const root = zoomInAfter((scroller) => {
    scroller.scrollLeft = 200;
  });
  // Still 434/600 across the now 1200 px page.
  expect(root.scrollLeft).toBeCloseTo(16 + 868 - 250);
});

it("keeps the middle of a page that fit the view when zooming in", () => {
  // At zoom 1 the 600 px page is centred in the 800 px view, 100 px in, so
  // the middle of the view is half way across it.
  const root = zoomInAfter((scroller) => {
    scroller.scrollLeft = 0;
  }, 800);
  // At zoom 2 the page is 1200 px wide and starts at the 16 px gutter.
  expect(root.scrollLeft).toBeCloseTo(16 + 600 - 400);
});

function scrollTo(root: HTMLElement, top: number) {
  root.scrollTop = top;
  act(() => {
    root.dispatchEvent(new Event("scroll"));
  });
}

it("reports the page showing most of itself", () => {
  const { document } = fakeDocument(10);
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  const root = layOut(container, () => 1);
  // Page 4 spans 3264-4064 and page 5 4080-4880: 100 px of 4, 284 px of 5.
  scrollTo(root, 3964);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(5);
  // 300 px of 4, 84 px of 5.
  scrollTo(root, 3764);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(4);
});

it("counts a short page shown whole over part of a taller one", () => {
  const { document } = fakeDocument(3);
  const onCurrentPageChange = vi.fn();
  const heights = [1000, 200, 1000];
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={heights.map((height) => ({ width: 600, height }))}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  const root = layOut(
    container,
    () => 1,
    () => 600,
  );
  // Pages 0-1000, 1016-1216 and 1232-2232, laid out by hand.
  const tops = [16, 1032, 1248];
  for (const page of container.querySelectorAll<HTMLElement>(
    "[data-page-index]",
  )) {
    const index = Number(page.getAttribute("data-page-index"));
    Object.defineProperties(page, {
      offsetTop: { get: () => tops[index] },
      offsetHeight: { get: () => heights[index] },
    });
  }
  Object.defineProperty(root, "scrollHeight", { get: () => 2264 });
  // 700-1300: 300 px of page 0 (half the view), all 200 px of page 1, and
  // 52 px of page 2. Page 1 shows the most of itself.
  scrollTo(root, 700);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(1);
  // 400-1000: page 0 fills the view, so it counts as shown whole.
  scrollTo(root, 400);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(0);
});

it("keeps the current page right for a page much taller than the viewer", () => {
  const { document } = fakeDocument(10);
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(10)}
      zoom={4}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  // At 400% a page is 3200 px in a 400 px viewer, so no intersection ratio
  // ever reaches a quarter. Page 2 spans 6432-9632.
  const root = layOut(container, () => 4);
  scrollTo(root, 9332);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(2);
  scrollTo(root, 9600);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(3);
});

it("reports the last page once the end is reached, even when others show as much", () => {
  const { document } = fakeDocument(10);
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  // Two whole pages fit at the bottom; without the end rule page 8 would win
  // the tie and Next would never reach page 9.
  const root = layOut(
    container,
    () => 1,
    () => 2000,
  );
  scrollTo(root, root.scrollHeight - 2000);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(9);
});

it("pages back from the last page when the last pages fit together", () => {
  const { document } = fakeDocument(10);
  const ref = createRef<PdfPageListHandle>();
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  const root = layOut(
    container,
    () => 1,
    () => 2000,
  );
  // Clamp scrolling at the end, as a browser does.
  let scrollTop = 0;
  Object.defineProperty(root, "scrollTop", {
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = Math.min(
        Math.max(0, value),
        root.scrollHeight - root.clientHeight,
      );
    },
  });
  act(() => ref.current?.scrollToPage(9));
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(9);
  // Page 8's top is past the end of the scroll, so the jump lands at the end.
  act(() => ref.current?.scrollToPage(8));
  act(() => {
    root.dispatchEvent(new Event("scroll"));
  });
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(8);
  act(() => ref.current?.scrollToPage(7));
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(7);
  // A scroll by the reader goes back to measuring.
  scrollTo(root, root.scrollHeight - root.clientHeight);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(9);
});

it("follows a highlight shown after a page jump, even at the same scroll end", () => {
  const { document } = fakeDocument(10);
  const ref = createRef<PdfPageListHandle>();
  const onCurrentPageChange = vi.fn();
  const highlights = [
    {
      id: "end",
      page: 9,
      x: 0.1,
      y: 0.9,
      w: 0.5,
      h: 0.05,
      variant: "line" as const,
      tone: "default" as const,
    },
  ];
  const { container } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      highlights={highlights}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  const root = layOut(
    container,
    () => 1,
    () => 2000,
  );
  let scrollTop = 0;
  Object.defineProperty(root, "scrollTop", {
    get: () => scrollTop,
    set: (value: number) => {
      scrollTop = Math.min(
        Math.max(0, value),
        root.scrollHeight - root.clientHeight,
      );
    },
  });
  // Both land at the end of the scroll.
  act(() => ref.current?.scrollToPage(8));
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(8);
  act(() => {
    ref.current?.scrollToHighlight("end");
  });
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(9);
});

it("updates the current page when the viewer changes height without scrolling", () => {
  const { document } = fakeDocument(10);
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  let height = 400;
  const root = layOut(
    container,
    () => 1,
    () => height,
  );
  // Page 2 spans 1648-2448 and page 3 2464-3264: 300 px of 2, 84 px of 3.
  scrollTo(root, 2148);
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(2);
  // Taller: 300 px of 2, all 800 of 3.
  height = 1200;
  act(() => viewerResized?.());
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(3);
});

it("reports the page jumped to without waiting for a scroll event", () => {
  const { document } = fakeDocument(10);
  const ref = createRef<PdfPageListHandle>();
  const onCurrentPageChange = vi.fn();
  const { container } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(10)}
      zoom={1}
      onCurrentPageChange={onCurrentPageChange}
    />,
  );
  layOut(container, () => 1);
  act(() => ref.current?.scrollToPage(6));
  expect(onCurrentPageChange).toHaveBeenLastCalledWith(6);
});

it("keeps the same spot of a later page across a zoom change", () => {
  const { document } = fakeDocument(10);
  let zoom = 1;
  const { container, rerender } = render(
    <PdfPageList document={document} pageSizes={sizes(10)} zoom={zoom} />,
  );
  const root = layOut(container, () => zoom);
  // A quarter of the way down page 3, which starts at 3 × 816.
  scrollTo(root, 3 * 816 + 200);
  zoom = 2;
  rerender(
    <PdfPageList document={document} pageSizes={sizes(10)} zoom={zoom} />,
  );
  expect(root.scrollTop).toBe(3 * 1616 + 400);
});

it("zooms around the page jumped to, even after the jump's scroll event", () => {
  const { document } = fakeDocument(200);
  const ref = createRef<PdfPageListHandle>();
  let zoom = 1;
  const { container, rerender } = render(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(200)}
      zoom={zoom}
    />,
  );
  const root = layOut(container, () => zoom);
  act(() => ref.current?.scrollToPage(100));
  // The browser fires the jump's scroll event before intersections update.
  act(() => {
    root.dispatchEvent(new Event("scroll"));
  });
  zoom = 1.5;
  rerender(
    <PdfPageList
      ref={ref}
      document={document}
      pageSizes={sizes(200)}
      zoom={zoom}
    />,
  );
  expect(root.scrollTop).toBe(100 * (1200 + 16));
});

it("cleans up a page that arrives after it has left the window", async () => {
  const { document } = fakeDocument(10);
  const late = { getViewport: vi.fn(), render: vi.fn(), cleanup: vi.fn() };
  let deliver!: () => void;
  (document.getPage as ReturnType<typeof vi.fn>).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        deliver = () => resolve(late);
      }),
  );
  render(<PdfPageList document={document} pageSizes={sizes(10)} zoom={1} />);
  show([0]);
  await flush();
  show([9]);
  await act(async () => deliver());
  expect(late.cleanup).toHaveBeenCalled();
  expect(late.render).not.toHaveBeenCalled();
});

const pageHighlights = [
  {
    id: "a",
    page: 2,
    x: 0,
    y: 0.1,
    w: 1,
    h: 0.02,
    variant: "line" as const,
    tone: "default" as const,
  },
  {
    id: "b",
    page: 0,
    x: 0,
    y: 0.5,
    w: 1,
    h: 0.02,
    variant: "line" as const,
    tone: "default" as const,
  },
];

it("re-renders only the pages that lose and gain the active highlight", () => {
  const { document } = fakeDocument(3);
  const overlay = vi.fn((_index: number) => null);
  // Stable inputs, as a real caller holds them: only the active id changes.
  const pageSizes = sizes(3);
  const { rerender } = render(
    <PdfPageList
      document={document}
      pageSizes={pageSizes}
      zoom={1}
      highlights={pageHighlights}
      activeHighlightId="b"
      renderPageOverlay={overlay}
    />,
  );
  overlay.mockClear();
  rerender(
    <PdfPageList
      document={document}
      pageSizes={pageSizes}
      zoom={1}
      highlights={pageHighlights}
      activeHighlightId="a"
      renderPageOverlay={overlay}
    />,
  );
  expect(overlay.mock.calls.map(([index]) => index).sort()).toEqual([0, 2]);
});

it("blends highlights into a page once it has painted, and keeps it through a zoom", async () => {
  const { document, tasks } = fakeDocument(1);
  const highlights = [
    { ...pageHighlights[1], page: 0 },
  ] as typeof pageHighlights;
  const { container, rerender } = render(
    <PdfPageList
      document={document}
      pageSizes={sizes(1)}
      zoom={1}
      highlights={highlights}
    />,
  );
  const blended = () =>
    container
      .querySelector('[data-highlight-id="b"]')
      ?.className.includes("mix-blend-multiply");
  expect(blended()).toBe(false);
  show([0]);
  await flush();
  expect(blended()).toBe(false);
  await act(async () => tasks[0]?.finish());
  expect(blended()).toBe(true);
  rerender(
    <PdfPageList
      document={document}
      pageSizes={sizes(1)}
      zoom={2}
      highlights={highlights}
    />,
  );
  await flush();
  expect(blended()).toBe(true);
  show([]);
  await flush();
  expect(blended()).toBe(false);
});

it("reads the page elements once, not on every scroll", async () => {
  const { document } = fakeDocument(20);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(20)} zoom={1} />,
  );
  const region = container.querySelector("section");
  if (!region) {
    throw new Error("no region");
  }
  const query = vi.spyOn(region, "querySelectorAll");
  for (let step = 0; step < 10; step++) {
    act(() => {
      region.scrollTop = step * 100;
      region.dispatchEvent(new Event("scroll"));
    });
  }
  expect(query.mock.calls.length).toBeLessThanOrEqual(1);
});
