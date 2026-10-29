import { act, renderHook } from "@testing-library/react";
import type { PdfOpening } from "@v1/lib/pdf/pdfjs";
import type { OpenedPdf, PdfSource } from "@v1/lib/pdf/types";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { beforeEach, expect, it, vi } from "vitest";
import { usePdfDocument } from "./usePdfDocument";

interface FakeOpening extends PdfOpening {
  source: PdfSource;
  password?: string;
  resolve: (value: OpenedPdf) => void;
  reject: (error: unknown) => void;
  destroy: ReturnType<typeof vi.fn>;
}

const openings: FakeOpening[] = [];

vi.mock("@v1/lib/pdf/pdfjs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@v1/lib/pdf/pdfjs")>();
  return {
    ...actual,
    openPdfDocument: (
      source: PdfSource,
      options: { password?: string } = {},
    ): PdfOpening => {
      let resolve!: (value: OpenedPdf) => void;
      let reject!: (error: unknown) => void;
      const promise = new Promise<OpenedPdf>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      const opening: FakeOpening = {
        source,
        password: options.password,
        promise,
        resolve,
        reject,
        destroy: vi.fn(),
      };
      openings.push(opening);
      return opening;
    },
  };
});

const document = { numPages: 2 } as unknown as PDFDocumentProxy;
const pageSizes = [
  { width: 612, height: 792 },
  { width: 792, height: 612 },
];
const url = (path: string): PdfSource => ({ kind: "url", url: path });
const passwordError = (code: number) =>
  Object.assign(new Error("password"), { name: "PasswordException", code });

function latest(): FakeOpening {
  const opening = openings.at(-1);
  if (!opening) {
    throw new Error("nothing was opened");
  }
  return opening;
}

beforeEach(() => {
  openings.length = 0;
});

it("is empty without a source and opens nothing", () => {
  const { result } = renderHook(() => usePdfDocument(null));
  expect(result.current.state).toEqual({ status: "empty" });
  expect(openings).toHaveLength(0);
});

it("goes from loading to ready with the page sizes", async () => {
  const { result } = renderHook(() => usePdfDocument(url("/a.pdf")));
  expect(result.current.state).toEqual({ status: "loading" });
  await act(async () => latest().resolve({ document, pageSizes }));
  expect(result.current.state).toEqual({
    status: "ready",
    document,
    pageSizes,
  });
});

it("does not reopen when re-rendered with an equal, new source object", () => {
  const { rerender } = renderHook(() => usePdfDocument(url("/a.pdf")));
  rerender();
  rerender();
  expect(openings).toHaveLength(1);
});

it("treats a document with no pages as empty", async () => {
  const { result } = renderHook(() => usePdfDocument(url("/a.pdf")));
  await act(async () => latest().resolve({ document, pageSizes: [] }));
  expect(result.current.state).toEqual({ status: "empty" });
});

it("fails with the message, and Retry opens the same source again", async () => {
  const { result } = renderHook(() => usePdfDocument(url("/a.pdf")));
  await act(async () => latest().reject(new Error("Network error")));
  expect(result.current.state).toEqual({
    status: "failed",
    message: "Network error",
  });

  act(() => result.current.retry());
  expect(result.current.state).toEqual({ status: "loading" });
  expect(openings).toHaveLength(2);
  expect(openings[0]?.destroy).toHaveBeenCalled();
  expect(latest().source).toEqual(url("/a.pdf"));
});

it("reports a non-PDF as unsupported", async () => {
  const { result } = renderHook(() => usePdfDocument(url("/a.txt")));
  await act(async () =>
    latest().reject(
      Object.assign(new Error("Invalid PDF"), { name: "InvalidPDFException" }),
    ),
  );
  expect(result.current.state).toEqual({ status: "unsupported" });
});

it("asks for a password, reopens with it, and flags a wrong one", async () => {
  const { result } = renderHook(() => usePdfDocument(url("/locked.pdf")));
  await act(async () => latest().reject(passwordError(1)));
  expect(result.current.state).toEqual({
    status: "password",
    incorrect: false,
  });

  act(() => result.current.submitPassword("wrong"));
  expect(latest().password).toBe("wrong");
  await act(async () => latest().reject(passwordError(2)));
  expect(result.current.state).toEqual({ status: "password", incorrect: true });

  act(() => result.current.submitPassword("right"));
  await act(async () => latest().resolve({ document, pageSizes }));
  expect(result.current.state.status).toBe("ready");
});

it("destroys the old load when the source changes, and ignores its result", async () => {
  const { result, rerender } = renderHook(
    ({ path }) => usePdfDocument(url(path)),
    { initialProps: { path: "/a.pdf" } },
  );
  const first = latest();
  rerender({ path: "/b.pdf" });
  expect(first.destroy).toHaveBeenCalledTimes(1);
  expect(result.current.state).toEqual({ status: "loading" });

  await act(async () => first.resolve({ document, pageSizes }));
  expect(result.current.state).toEqual({ status: "loading" });
  expect(latest().source).toEqual(url("/b.pdf"));
});

it("forgets the password when the source changes", async () => {
  const { result, rerender } = renderHook(
    ({ path }) => usePdfDocument(url(path)),
    { initialProps: { path: "/a.pdf" } },
  );
  await act(async () => latest().reject(passwordError(1)));
  act(() => result.current.submitPassword("secret"));
  rerender({ path: "/b.pdf" });
  expect(latest().password).toBeUndefined();
});

it("destroys the load on unmount", () => {
  const { unmount } = renderHook(() => usePdfDocument(url("/a.pdf")));
  unmount();
  expect(latest().destroy).toHaveBeenCalledTimes(1);
});
