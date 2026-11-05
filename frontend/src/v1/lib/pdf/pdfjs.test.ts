import type { PDFDocumentProxy } from "pdfjs-dist";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pdfjsMock = vi.hoisted(() => ({
  getDocument: vi.fn(),
  GlobalWorkerOptions: { workerSrc: "" },
}));
vi.mock("pdfjs-dist", () => pdfjsMock);
vi.mock("pdfjs-dist/build/pdf.worker.min.js?url", () => ({
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

  it("passes the URL, credentials and headers through", () => {
    expect(
      toDocumentParams({
        kind: "url",
        url: "/a.pdf",
        withCredentials: true,
        httpHeaders: { Authorization: "Bearer x" },
      }),
    ).toEqual({
      isEvalSupported: false,
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

  it("keeps the document open when a page cannot be read", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const sizes = [
      { width: 1, height: 1 },
      { width: 600, height: 800 },
      { width: 700, height: 900 },
    ];
    const document = {
      numPages: 3,
      getPage: async (n: number) => {
        if (n !== 3) {
          throw new Error("damaged page");
        }
        return { getViewport: () => sizes[n - 1] };
      },
    } as unknown as PDFDocumentProxy;
    // Pages 1 and 2 borrow page 3's size; nothing comes before them.
    await expect(readPageSizes(document)).resolves.toEqual([
      sizes[2],
      sizes[2],
      sizes[2],
    ]);
    expect(error).toHaveBeenCalledTimes(2);
    error.mockRestore();
  });

  it("fails when no page can be read", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const document = {
      numPages: 2,
      getPage: async () => {
        throw new Error("damaged file");
      },
    } as unknown as PDFDocumentProxy;
    await expect(readPageSizes(document)).rejects.toThrow("damaged file");
    error.mockRestore();
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

  it("keeps the URL, and any token in it, out of a server error", () => {
    const url = "https://bucket.example/doc.pdf?X-Amz-Signature=secret";
    const missing = classifyLoadError(
      Object.assign(new Error(`Missing PDF "${url}".`), {
        name: "MissingPDFException",
      }),
    );
    const forbidden = classifyLoadError(
      Object.assign(
        new Error(
          `Unexpected server response (403) while retrieving PDF "${url}".`,
        ),
        { name: "UnexpectedResponseException", status: 403 },
      ),
    );
    expect(missing).toEqual({
      kind: "failed",
      message: "The document wasn't found.",
    });
    expect(forbidden).toEqual({
      kind: "failed",
      message: "The server returned an error (403).",
    });
  });

  it("shows a plain message for anything else, and logs pdf.js's own", () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const raw = named("UnknownErrorException");
    const failed = {
      kind: "failed",
      message: "The document couldn't be opened.",
    };
    expect(classifyLoadError(raw)).toEqual(failed);
    expect(classifyLoadError("offline")).toEqual(failed);
    expect(error).toHaveBeenCalledWith(expect.any(String), raw);
    error.mockRestore();
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

  it("asks for a password on the same load, and says when one was wrong", async () => {
    const task = Object.assign(deferredTask(), {
      onPassword: null as
        | null
        | ((update: (password: string) => void, reason: number) => void),
    });
    pdfjsMock.getDocument.mockReturnValue(task);
    const prompts: { incorrect: boolean; submit: (p: string) => void }[] = [];
    const opening = openPdfDocument(
      { kind: "url", url: "/locked.pdf" },
      { onPassword: (prompt) => prompts.push(prompt) },
    );
    opening.promise.catch(() => undefined);
    await vi.waitFor(() => expect(task.onPassword).not.toBeNull());
    const update = vi.fn();
    task.onPassword?.(update, 1);
    prompts[0]?.submit("wrong");
    task.onPassword?.(update, 2);
    expect(prompts.map((prompt) => prompt.incorrect)).toEqual([false, true]);
    expect(update).toHaveBeenCalledWith("wrong");
    // One download for all of it.
    expect(pdfjsMock.getDocument).toHaveBeenCalledTimes(1);
    expect(pdfjsMock.getDocument.mock.calls[0]?.[0]).not.toHaveProperty(
      "password",
    );

    opening.destroy();
    prompts[1]?.submit("late");
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("handles a destroy that fails because the worker is already gone", async () => {
    const task = deferredTask();
    const handled = vi.fn();
    task.destroy.mockImplementation(() => {
      const failed = Promise.reject(new Error("Worker was destroyed"));
      const original = failed.catch.bind(failed);
      failed.catch = (onRejected) => {
        handled();
        return original(onRejected);
      };
      return failed;
    });
    pdfjsMock.getDocument.mockReturnValue(task);
    const opening = openPdfDocument({ kind: "url", url: "/a.pdf" });
    opening.promise.catch(() => undefined);
    await vi.waitFor(() => expect(pdfjsMock.getDocument).toHaveBeenCalled());
    opening.destroy();
    expect(handled).toHaveBeenCalled();
  });

  it("never starts a load that was destroyed while pdf.js was loading", async () => {
    const opening = openPdfDocument({ kind: "url", url: "/a.pdf" });
    opening.destroy();
    await expect(opening.promise).rejects.toThrow();
    expect(pdfjsMock.getDocument).not.toHaveBeenCalled();
  });
});

describe("loadPdfjs", () => {
  it("tries again after a failed load instead of keeping the failure", async () => {
    vi.resetModules();
    let fail = true;
    vi.doMock("pdfjs-dist", () => {
      if (fail) {
        throw new Error("chunk failed");
      }
      return pdfjsMock;
    });
    const { loadPdfjs } = await import("./pdfjs");
    await expect(loadPdfjs()).rejects.toThrow();
    fail = false;
    pdfjsMock.GlobalWorkerOptions.workerSrc = "";
    await expect(loadPdfjs()).resolves.toBeTruthy();
    expect(pdfjsMock.GlobalWorkerOptions.workerSrc).toBe(
      "/assets/pdf.worker.min.js",
    );
    vi.doUnmock("pdfjs-dist");
  });
});
