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
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    {} as CanvasRenderingContext2D,
  );
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
  const { document, render: renderPage } = fakeDocument(1);
  const { container } = render(
    <PdfPageList document={document} pageSizes={sizes(1)} zoom={1} />,
  );
  show([0]);
  await flush();
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
