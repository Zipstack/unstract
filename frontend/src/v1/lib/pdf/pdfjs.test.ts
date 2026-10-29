import type { PDFDocumentProxy } from "pdfjs-dist";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pdfjsMock = vi.hoisted(() => ({
  getDocument: vi.fn(),
  GlobalWorkerOptions: { workerSrc: "" },
}));
vi.mock("pdfjs-dist/legacy/build/pdf.js", () => pdfjsMock);
vi.mock("pdfjs-dist/legacy/build/pdf.worker.min.js?url", () => ({
  default: "/assets/pdf.worker.min.js",
}));

import {
  classifyLoadError,
  openPdfDocument,
  pdfSourceKey,
  readPageSizes,
  toDocumentParams,
} from "./pdfjs";

function fakeDocument(sizes: { width: number; height: number }[]) {
  const pending: (() => void)[] = [];
  const getPage = vi.fn(
    (n: number) =>
      new Promise((resolve) => {
        pending.push(() => resolve({ getViewport: () => sizes[n - 1] }));
      }),
  );
  const document = {
    numPages: sizes.length,
    getPage,
  } as unknown as PDFDocumentProxy;
  const flush = () => {
    for (const resolve of pending.splice(0)) {
      resolve();
    }
  };
  return { document, getPage, flush };
}

function deferredTask() {
  let resolve!: (doc: PDFDocumentProxy) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<PDFDocumentProxy>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject, destroy: vi.fn(async () => undefined) };
}

beforeEach(() => {
  pdfjsMock.getDocument.mockReset();
});

describe("toDocumentParams", () => {
  it("never allows eval, for URL and data sources", () => {
    expect(
      toDocumentParams({ kind: "url", url: "/a.pdf" }).isEvalSupported,
    ).toBe(false);
    expect(
      toDocumentParams({ kind: "data", data: new Uint8Array([1]) })
        .isEvalSupported,
    ).toBe(false);
  });

  it("passes the URL, credentials, headers and password through", () => {
    expect(
      toDocumentParams(
        {
          kind: "url",
          url: "/a.pdf",
          withCredentials: true,
          httpHeaders: { Authorization: "Bearer x" },
        },
        "secret",
      ),
    ).toEqual({
      isEvalSupported: false,
      password: "secret",
      url: "/a.pdf",
      withCredentials: true,
      httpHeaders: { Authorization: "Bearer x" },
    });
  });

  it("copies bytes, so the worker transfer cannot empty the caller's buffer", () => {
    const data = new Uint8Array([1, 2, 3]);
    const params = toDocumentParams({ kind: "data", data });
    expect(params.data).not.toBe(data);
    expect([...(params.data as Uint8Array)]).toEqual([1, 2, 3]);

    const buffer = new Uint8Array([4, 5]).buffer;
    const fromBuffer = toDocumentParams({ kind: "data", data: buffer });
    expect([...(fromBuffer.data as Uint8Array)]).toEqual([4, 5]);
    expect((fromBuffer.data as Uint8Array).buffer).not.toBe(buffer);
  });
});

describe("pdfSourceKey", () => {
  it("is stable for equal URL sources, whatever the header order", () => {
    const a = pdfSourceKey({
      kind: "url",
      url: "/a.pdf",
      httpHeaders: { A: "1", B: "2" },
    });
    const b = pdfSourceKey({
      kind: "url",
      url: "/a.pdf",
      httpHeaders: { B: "2", A: "1" },
    });
    expect(a).toBe(b);
    expect(pdfSourceKey({ kind: "url", url: "/b.pdf" })).not.toBe(a);
    expect(
      pdfSourceKey({ kind: "url", url: "/a.pdf", withCredentials: true }),
    ).not.toBe(pdfSourceKey({ kind: "url", url: "/a.pdf" }));
  });

  it("follows the buffer's identity for data sources", () => {
    const data = new Uint8Array([1]);
    expect(pdfSourceKey({ kind: "data", data })).toBe(
      pdfSourceKey({ kind: "data", data }),
    );
    expect(pdfSourceKey({ kind: "data", data: new Uint8Array([1]) })).not.toBe(
      pdfSourceKey({ kind: "data", data }),
    );
    expect(pdfSourceKey(null)).toBe("none");
  });
});

describe("readPageSizes", () => {
  it("requests pages in parallel and returns them in page order", async () => {
    const sizes = Array.from({ length: 5 }, (_, i) => ({
      width: 600 + i,
      height: 800,
    }));
    const { document, getPage, flush } = fakeDocument(sizes);
    const result = readPageSizes(document, 3);
    await Promise.resolve();
    // Three requests are in flight before any has answered.
    expect(getPage).toHaveBeenCalledTimes(3);
    for (let i = 0; i < 5; i++) {
      flush();
      await new Promise((r) => setTimeout(r, 0));
    }
    await expect(result).resolves.toEqual(sizes);
    expect(getPage.mock.calls.map(([n]) => n)).toEqual([1, 2, 3, 4, 5]);
  });
});

describe("classifyLoadError", () => {
  const named = (name: string, extra: object = {}) =>
    Object.assign(new Error("boom"), { name }, extra);

  it("tells a missing password from a wrong one", () => {
    expect(classifyLoadError(named("PasswordException", { code: 1 }))).toEqual({
      kind: "password",
      incorrect: false,
    });
    expect(classifyLoadError(named("PasswordException", { code: 2 }))).toEqual({
      kind: "password",
      incorrect: true,
    });
  });

  it("reads a file that is not a PDF as unsupported", () => {
    expect(classifyLoadError(named("InvalidPDFException"))).toEqual({
      kind: "unsupported",
    });
  });

  it("reports anything else as a failure with its message", () => {
    expect(classifyLoadError(named("MissingPDFException"))).toEqual({
      kind: "failed",
      message: "boom",
    });
    expect(classifyLoadError("offline")).toEqual({
      kind: "failed",
      message: "offline",
    });
  });
});

describe("openPdfDocument", () => {
  it("points pdf.js at the bundled worker and resolves with page sizes", async () => {
    const task = deferredTask();
    pdfjsMock.getDocument.mockReturnValue(task);
    const opening = openPdfDocument({ kind: "url", url: "/a.pdf" });
    const document = {
      numPages: 1,
      getPage: async () => ({ getViewport: () => ({ width: 10, height: 20 }) }),
    } as unknown as PDFDocumentProxy;
    await vi.waitFor(() => expect(pdfjsMock.getDocument).toHaveBeenCalled());
    expect(pdfjsMock.GlobalWorkerOptions.workerSrc).toBe(
      "/assets/pdf.worker.min.js",
    );
    expect(pdfjsMock.getDocument.mock.calls[0]?.[0]).toMatchObject({
      url: "/a.pdf",
      isEvalSupported: false,
    });
    task.resolve(document);
    await expect(opening.promise).resolves.toEqual({
      document,
      pageSizes: [{ width: 10, height: 20 }],
    });
  });

  it("destroys the loading task once, however often destroy is called", async () => {
    const task = deferredTask();
    pdfjsMock.getDocument.mockReturnValue(task);
    const opening = openPdfDocument({ kind: "url", url: "/a.pdf" });
    opening.promise.catch(() => undefined);
    await vi.waitFor(() => expect(pdfjsMock.getDocument).toHaveBeenCalled());
    opening.destroy();
    opening.destroy();
    expect(task.destroy).toHaveBeenCalledTimes(1);
  });

  it("never starts a load that was destroyed while pdf.js was loading", async () => {
    const opening = openPdfDocument({ kind: "url", url: "/a.pdf" });
    opening.destroy();
    await expect(opening.promise).rejects.toThrow();
    expect(pdfjsMock.getDocument).not.toHaveBeenCalled();
  });
});
