import { act, render } from "@testing-library/react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PdfPageList } from "./PdfPageList";

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
  show(indexes: number[]) {
    const entries = [...this.targets].map((target) => ({
      target,
      isIntersecting: indexes.includes(
        Number(target.getAttribute("data-page-index")),
      ),
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

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
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
