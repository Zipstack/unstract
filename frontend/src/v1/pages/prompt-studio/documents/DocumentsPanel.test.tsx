import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { type NotifyInput, setNotifier } from "@v1/lib/notify";
import { setOrganizationId } from "@v1/services/context";
import {
  type PromptDocument,
  promptDocumentQueries,
} from "@v1/services/promptDocuments";
import {
  apiPath,
  DEFAULT_SESSION,
  delay,
  expectNoA11yViolations,
  HttpResponse,
  http,
  mockApi,
  type RenderV1Options,
  renderV1,
} from "@v1/test";
import {
  makeDocument,
  promptDocumentFixtures,
  TOOL_ID,
  uploadedFixture,
} from "@v1/test/fixtures/promptDocuments";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentsPanel, type DocumentsPanelProps } from "./DocumentsPanel";

const ORG = DEFAULT_SESSION;
const LIST = apiPath(ORG, "/prompt-studio/prompt-document/");
const FILE = apiPath(ORG, `/prompt-studio/file/${TOOL_ID}`);
const INDEX = apiPath(ORG, `/prompt-studio/index-document/${TOOL_ID}`);

let shown: NotifyInput[] = [];
let unregister: () => void = () => undefined;

beforeEach(() => {
  setOrganizationId(ORG.organization.id);
  shown = [];
  unregister = setNotifier({
    show: (input) => {
      shown.push(input);
      return String(shown.length);
    },
    dismiss: () => undefined,
  });
});
afterEach(() => {
  unregister();
  setOrganizationId(null);
});

/** A list endpoint whose rows the test can change between reads. */
function serveList(initial: readonly PromptDocument[]) {
  let rows = initial;
  mockApi(http.get(LIST, () => HttpResponse.json(rows)));
  return (next: readonly PromptDocument[]) => {
    rows = next;
  };
}

function renderPanel({
  userEventOptions,
  ...props
}: Partial<DocumentsPanelProps> &
  Readonly<{
    userEventOptions?: RenderV1Options["userEventOptions"];
  }> = {}) {
  return renderV1(<DocumentsPanel toolId={TOOL_ID} {...props} />, {
    // The picker's accept is checked by the panel itself, not the browser.
    userEventOptions: { applyAccept: false, ...userEventOptions },
  });
}

/** The failed fixture's document in another state. */
const amex = (state: Parameters<typeof makeDocument>[0]) =>
  makeDocument({
    document_id: promptDocumentFixtures.failed.document_id,
    document_name: promptDocumentFixtures.failed.document_name,
    size_bytes: promptDocumentFixtures.failed.size_bytes,
    page_count: promptDocumentFixtures.failed.page_count,
    ...state,
  });

const pdf = (name: string) =>
  new File(["%PDF-1.4"], name, { type: "application/pdf" });

describe("the list (D04)", () => {
  it("shows each document with size · pages and its state, and a footer", async () => {
    serveList(promptDocumentFixtures.list);
    renderPanel();
    const list = await screen.findByRole("list", { name: "Documents" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(rows[0]).toHaveTextContent("CreditCardStatement.pdf");
    expect(rows[0]).toHaveTextContent("412 KB · 6 pages");
    expect(rows[0]).toHaveTextContent("Parsed");
    expect(rows[3]).toHaveTextContent("Pending");
    expect(
      screen.getByText("4 documents · 14 pages total"),
    ).toBeInTheDocument();
    expect(screen.getByText("Supports PDF · up to 200 MB")).toBeInTheDocument();
  });

  it("calls onView with the document's id", async () => {
    serveList(promptDocumentFixtures.list);
    const onView = vi.fn();
    const { user } = renderPanel({ onView });
    await user.click(
      await screen.findByRole("button", { name: "View boa_march_2026.pdf" }),
    );
    expect(onView).toHaveBeenCalledWith("d0000000-0000-4000-8000-000000000002");
  });

  it("has no accessibility violations", async () => {
    serveList([
      ...promptDocumentFixtures.list.slice(0, 3),
      promptDocumentFixtures.failed,
    ]);
    const { container } = renderPanel({ onView: () => undefined });
    await screen.findByRole("list", { name: "Documents" });
    await expectNoA11yViolations(container);
  });
});

describe("empty (D05)", () => {
  it("explains that prompts need a document", async () => {
    serveList([]);
    renderPanel();
    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Prompts run against every document in this list. Add at least one before you write a prompt.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("0 documents")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Upload documents" }),
    ).toBeEnabled();
  });

  it("refuses uploads, saying why, until the tool has a default profile", async () => {
    serveList([]);
    const { user } = renderPanel({
      uploadBlockedReason:
        "Set the default LLM profile before uploading a document",
    });
    expect(
      await screen.findByRole("button", { name: "Upload documents" }),
    ).toBeDisabled();
    const zone = screen.getByRole("button", {
      name: "Drag & drop files here, or click to browse",
    });
    expect(zone).toHaveAttribute("aria-disabled", "true");
    expect(zone).toHaveAccessibleDescription(
      "Set the default LLM profile before uploading a document",
    );
    const input = screen.getByTestId("file-drop-input");
    const click = vi.spyOn(input, "click");
    await user.click(zone);
    expect(click).not.toHaveBeenCalled();
  });
});

describe("uploads (D06)", () => {
  it("shows the file uploading, then lists it", async () => {
    const setRows = serveList(promptDocumentFixtures.list.slice(0, 2));
    let release: () => void = () => undefined;
    const arrived = new Promise<void>((resolve) => {
      release = resolve;
    });
    const posted: string[] = [];
    mockApi(
      http.post(FILE, async ({ request }) => {
        posted.push(((await request.formData()).get("file") as File).name);
        await arrived;
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    const onUploaded = vi.fn();
    const { user } = renderPanel({ onUploaded });
    await screen.findByText("2 documents · 8 pages total");
    await user.upload(
      screen.getByTestId("file-drop-input"),
      pdf("new_statement.pdf"),
    );

    expect(
      await screen.findByRole("progressbar", {
        name: "Uploading new_statement.pdf",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("1 uploading · 2 documents")).toBeInTheDocument();

    setRows([
      ...promptDocumentFixtures.list.slice(0, 2),
      makeDocument({
        document_id: uploadedFixture.document_id,
        document_name: uploadedFixture.document_name,
        status: "pending",
      }),
    ]);
    release();
    expect(
      await screen.findByText("3 documents · 14 pages total"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(posted).toEqual(["new_statement.pdf"]);
    expect(onUploaded).toHaveBeenCalledWith(uploadedFixture);
  });

  it("uploads several files one at a time", async () => {
    serveList([]);
    const order: string[] = [];
    let inFlight = 0;
    mockApi(
      http.post(FILE, async ({ request }) => {
        inFlight += 1;
        expect(inFlight).toBe(1);
        order.push(((await request.formData()).get("file") as File).name);
        await delay(5);
        inFlight -= 1;
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    const { user } = renderPanel();
    await screen.findByText("No documents yet");
    await user.upload(screen.getByTestId("file-drop-input"), [
      pdf("a.pdf"),
      pdf("b.pdf"),
    ]);
    await waitFor(() => expect(order).toEqual(["a.pdf", "b.pdf"]));
  });

  it("refuses a file the backend would refuse, without sending it", async () => {
    serveList(promptDocumentFixtures.list);
    const posted = vi.fn();
    mockApi(http.post(FILE, posted));
    const { user } = renderPanel();
    await screen.findByText("4 documents · 14 pages total");
    await user.upload(screen.getByTestId("file-drop-input"), [
      new File(["x"], "scan.png", { type: "image/png" }),
      pdf("CreditCardStatement.pdf"),
    ]);
    expect(shown.map((toast) => toast.description)).toEqual([
      "scan.png is not a supported type. Upload PDF.",
      "A document named CreditCardStatement already exists.",
    ]);
    expect(posted).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("drops the row and reports a failed upload", async () => {
    serveList([]);
    mockApi(
      http.post(FILE, () =>
        HttpResponse.json(
          {
            type: "validation_error",
            errors: [
              { code: "invalid", detail: "File too large.", attr: "file" },
            ],
          },
          { status: 400 },
        ),
      ),
    );
    const onUploaded = vi.fn();
    const { user } = renderPanel({ onUploaded });
    await screen.findByText("No documents yet");
    await user.upload(screen.getByTestId("file-drop-input"), pdf("a.pdf"));
    await waitFor(() => expect(shown).toHaveLength(1));
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("0 documents")).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("reads the list again when an upload's answer cannot be read", async () => {
    let reads = 0;
    mockApi(
      http.get(LIST, () => {
        reads += 1;
        return HttpResponse.json([]);
      }),
      // The file is stored, but the answer is not the expected shape.
      http.post(FILE, () => HttpResponse.json({ data: [] })),
    );
    const { user } = renderPanel();
    await screen.findByText("No documents yet");
    const before = reads;
    await user.upload(screen.getByTestId("file-drop-input"), pdf("a.pdf"));
    await waitFor(() => expect(reads).toBe(before + 1));
  });

  it("refuses a second file with the name of one still uploading", async () => {
    serveList([]);
    const posted: string[] = [];
    mockApi(
      http.post(FILE, async ({ request }) => {
        posted.push(((await request.formData()).get("file") as File).name);
        await new Promise(() => undefined);
        return HttpResponse.json({});
      }),
    );
    const { user } = renderPanel();
    await screen.findByText("No documents yet");
    const input = screen.getByTestId("file-drop-input");
    await user.upload(input, pdf("a.pdf"));
    await waitFor(() => expect(posted).toEqual(["a.pdf"]));
    await user.upload(input, pdf("a.pdf"));
    expect(shown.map((toast) => toast.description)).toEqual([
      "A document named a already exists.",
    ]);
  });

  it("uploads dropped files", async () => {
    serveList([]);
    const posted: string[] = [];
    mockApi(
      http.post(FILE, async ({ request }) => {
        posted.push(((await request.formData()).get("file") as File).name);
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    renderPanel();
    await screen.findByText("No documents yet");
    fireEvent.drop(
      screen.getByRole("button", {
        name: "Drag & drop files here, or click to browse",
      }),
      { dataTransfer: { files: [pdf("dropped.pdf")] } },
    );
    await waitFor(() => expect(posted).toEqual(["dropped.pdf"]));
  });

  it("ignores a drop while uploads are refused", async () => {
    serveList([]);
    const posted = vi.fn();
    mockApi(http.post(FILE, posted));
    renderPanel({ uploadBlockedReason: "Set the default LLM profile first" });
    await screen.findByText("No documents yet");
    fireEvent.drop(
      screen.getByRole("button", {
        name: "Drag & drop files here, or click to browse",
      }),
      { dataTransfer: { files: [pdf("dropped.pdf")] } },
    );
    await delay(20);
    expect(posted).not.toHaveBeenCalled();
  });

  it("refuses uploads until the list has loaded, so a same-named file is never sent", async () => {
    mockApi(http.get(LIST, () => HttpResponse.json({}, { status: 500 })));
    const posted = vi.fn();
    mockApi(http.post(FILE, posted));
    const { user } = renderPanel();
    expect(
      await screen.findByText(
        "Uploads wait for the document list. Retry it first.",
      ),
    ).toBeInTheDocument();
    await user.upload(screen.getByTestId("file-drop-input"), pdf("a.pdf"));
    await delay(20);
    expect(posted).not.toHaveBeenCalled();
  });

  it("starts afresh for another tool and sends its files there", async () => {
    serveList([]);
    const posted: string[] = [];
    const other = apiPath(ORG, "/prompt-studio/file/other-tool");
    mockApi(
      http.post(FILE, async () => {
        posted.push("first");
        await new Promise(() => undefined);
        return HttpResponse.json({});
      }),
      http.post(other, () => {
        posted.push("other");
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    const { user, rerender } = renderPanel();
    await screen.findByText("No documents yet");
    await user.upload(screen.getByTestId("file-drop-input"), pdf("a.pdf"));
    await waitFor(() => expect(posted).toEqual(["first"]));
    rerender(<DocumentsPanel toolId="other-tool" />);
    await screen.findByText("No documents yet");
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    await user.upload(screen.getByTestId("file-drop-input"), pdf("b.pdf"));
    await waitFor(() => expect(posted).toEqual(["first", "other"]));
  });

  it("keeps uploading, and says so, when the workspace's callback throws", async () => {
    serveList([]);
    const posted: string[] = [];
    mockApi(
      http.post(FILE, async ({ request }) => {
        posted.push(((await request.formData()).get("file") as File).name);
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    const onUploaded = vi.fn(() => {
      throw new Error("boom");
    });
    const { user } = renderPanel({ onUploaded });
    await screen.findByText("No documents yet");
    await user.upload(screen.getByTestId("file-drop-input"), [
      pdf("a.pdf"),
      pdf("b.pdf"),
    ]);
    await waitFor(() => expect(posted).toEqual(["a.pdf", "b.pdf"]));
    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument(),
    );
    expect(shown).not.toHaveLength(0);
  });

  it("does not report an upload to a panel that has gone", async () => {
    serveList([]);
    let release: () => void = () => undefined;
    const arrived = new Promise<void>((resolve) => {
      release = resolve;
    });
    mockApi(
      http.post(FILE, async () => {
        await arrived;
        return HttpResponse.json({ data: [uploadedFixture] });
      }),
    );
    const onUploaded = vi.fn();
    const { user, unmount } = renderPanel({ onUploaded });
    await screen.findByText("No documents yet");
    await user.upload(screen.getByTestId("file-drop-input"), pdf("a.pdf"));
    await screen.findByRole("progressbar");
    unmount();
    release();
    await delay(30);
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it("keeps uploads open when a refresh fails with the list on screen", async () => {
    let failing = false;
    mockApi(
      http.get(LIST, () =>
        failing
          ? HttpResponse.json({}, { status: 503 })
          : HttpResponse.json(promptDocumentFixtures.list),
      ),
    );
    const posted = vi.fn(() => HttpResponse.json({ data: [uploadedFixture] }));
    mockApi(http.post(FILE, posted));
    const { user, queryClient } = renderPanel();
    await screen.findByText("4 documents · 14 pages total");
    failing = true;
    await queryClient.refetchQueries();
    expect(
      screen.queryByText("Uploads wait for the document list. Retry it first."),
    ).not.toBeInTheDocument();
    await user.upload(screen.getByTestId("file-drop-input"), pdf("new.pdf"));
    await waitFor(() => expect(posted).toHaveBeenCalledTimes(1));
  });
});

describe("parse failure (D07)", () => {
  it("shows the extractor's reason with the two suggestions", async () => {
    serveList([promptDocumentFixtures.failed, makeDocument()]);
    renderPanel();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("amex_jan_2026.pdf could not be parsed");
    expect(alert).toHaveTextContent(
      "LLM Whisperer V2 returned no text. Try a higher-resolution file, or switch the text extractor in Settings.",
    );
    expect(screen.getByText("305 KB · 0 pages parsed")).toBeInTheDocument();
    expect(screen.getByText("1 failed · 1 document")).toBeInTheDocument();
    // As drawn: no "Documents N" heading while a document has failed.
    expect(
      screen.queryByRole("heading", { name: /Documents/ }),
    ).not.toBeInTheDocument();
  });

  it("says so when the backend withholds the reason", async () => {
    serveList([amex({ status: "failed", reason: null })]);
    renderPanel();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No reason is available.",
    );
  });

  it("retries indexing, shows it processing, and settles on the new state", async () => {
    const setRows = serveList([promptDocumentFixtures.failed]);
    const indexed = vi.fn();
    mockApi(
      http.post(INDEX, async ({ request }) => {
        indexed(await request.json());
        return HttpResponse.json({ status: "accepted" }, { status: 202 });
      }),
    );
    const { user, queryClient } = renderPanel();
    mockApi(
      http.get(FILE, () =>
        HttpResponse.json({ data: "old", mime_type: "text/plain" }),
      ),
    );
    const extractQuery = promptDocumentQueries.content({
      toolId: TOOL_ID,
      documentId: promptDocumentFixtures.failed.document_id,
      view: "EXTRACT",
    });
    const extract = extractQuery.queryKey;
    await queryClient.prefetchQuery(extractQuery);
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    expect(indexed).toHaveBeenCalledWith({
      document_id: promptDocumentFixtures.failed.document_id,
    });
    expect(await screen.findByText("Processing")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Remove amex_jan_2026.pdf" }),
    ).toBeDisabled();

    expect(
      screen.getByRole("button", { name: "Index amex_jan_2026.pdf again" }),
    ).toBeDisabled();
    expect(queryClient.getQueryState(extract)?.isInvalidated).toBe(false);

    setRows([amex({ status: "indexed" })]);
    await queryClient.refetchQueries();
    expect(await screen.findByText("Parsed")).toBeInTheDocument();
    // The re-index may have changed the extracted text.
    expect(queryClient.getQueryState(extract)?.isInvalidated).toBe(true);
  });

  describe("with a clock", () => {
    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("polls while a re-index changes nothing, and stops after the wait", async () => {
      let reads = 0;
      mockApi(
        http.get(LIST, () => {
          reads += 1;
          return HttpResponse.json([amex({ status: "indexed" })]);
        }),
        http.post(INDEX, () => HttpResponse.json({}, { status: 202 })),
      );
      const { user } = renderPanel({
        userEventOptions: { advanceTimers: vi.advanceTimersByTime },
      });
      await user.click(
        await screen.findByRole("button", {
          name: "Index amex_jan_2026.pdf again",
        }),
      );
      expect(await screen.findByText("Processing")).toBeInTheDocument();
      const before = reads;
      await act(() => vi.advanceTimersByTimeAsync(5_000));
      await waitFor(() => expect(reads).toBe(before + 1));
      await act(() => vi.advanceTimersByTimeAsync(170_000));
      expect(screen.getByText("Processing")).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(10_000));
      expect(await screen.findByText("Parsed")).toBeInTheDocument();
      const after = reads;
      await act(() => vi.advanceTimersByTimeAsync(20_000));
      expect(reads).toBe(after);
    });

    it("stops waiting after the wait even while the list keeps failing", async () => {
      let failing = false;
      mockApi(
        http.get(LIST, () =>
          failing
            ? HttpResponse.json({}, { status: 503 })
            : HttpResponse.json([amex({ status: "indexed" })]),
        ),
        http.post(INDEX, () => HttpResponse.json({}, { status: 202 })),
      );
      const { user } = renderPanel({
        userEventOptions: { advanceTimers: vi.advanceTimersByTime },
      });
      await user.click(
        await screen.findByRole("button", {
          name: "Index amex_jan_2026.pdf again",
        }),
      );
      expect(await screen.findByText("Processing")).toBeInTheDocument();
      failing = true;
      await act(() => vi.advanceTimersByTimeAsync(185_000));
      expect(await screen.findByText("Parsed")).toBeInTheDocument();
    });
  });

  it("stops processing when the index request fails", async () => {
    serveList([promptDocumentFixtures.failed]);
    mockApi(http.post(INDEX, () => HttpResponse.json({}, { status: 500 })));
    const { user } = renderPanel();
    await user.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(shown).toHaveLength(1));
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("stops processing for each failed request when two overlap", async () => {
    const second = amex({ status: "pending" });
    const first = makeDocument({ status: "pending" });
    serveList([first, second]);
    mockApi(
      http.post(INDEX, async ({ request }) => {
        const { document_id } = (await request.json()) as {
          document_id: string;
        };
        // The first request fails after the second has started.
        await delay(document_id === first.document_id ? 30 : 0);
        return document_id === first.document_id
          ? HttpResponse.json({}, { status: 500 })
          : HttpResponse.json({ status: "accepted" }, { status: 202 });
      }),
    );
    const { user } = renderPanel();
    await user.click(
      await screen.findByRole("button", {
        name: "Index CreditCardStatement.pdf again",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "Index amex_jan_2026.pdf again" }),
    );
    await waitFor(() => expect(shown).toHaveLength(1));
    const rows = within(
      screen.getByRole("list", { name: "Documents" }),
    ).getAllByRole("listitem");
    await waitFor(() => expect(rows[0]).toHaveTextContent("Pending"));
    expect(rows[1]).toHaveTextContent("Processing");
  });

  it("shows processing for ids the workspace says are indexing", async () => {
    serveList([makeDocument({ status: "pending" })]);
    renderPanel({
      indexingIds: new Set(["d0000000-0000-4000-8000-000000000001"]),
    });
    expect(await screen.findByText("Processing")).toBeInTheDocument();
  });
});

describe("remove (D08)", () => {
  const prompts = [1, 2, 3, 4].map(() => ({
    coverage: promptDocumentFixtures.list.map(
      (document) => document.document_id,
    ),
  }));

  it("asks, with the coverage drop, then removes the document", async () => {
    const setRows = serveList(promptDocumentFixtures.list);
    const ask = vi.spyOn(window, "confirm").mockReturnValue(true);
    let body: unknown = null;
    mockApi(
      http.delete(FILE, async ({ request }) => {
        body = await request.json();
        setRows(promptDocumentFixtures.list.slice(0, 3));
        return HttpResponse.json("File deleted succesfully.");
      }),
    );
    const onRemoved = vi.fn();
    const { user } = renderPanel({ prompts, onRemoved });
    await user.click(
      await screen.findByRole("button", { name: "Remove amex_jan_2026.pdf" }),
    );
    expect(ask).toHaveBeenCalledWith(
      "Remove amex_jan_2026.pdf?\n\nThe document and every prompt output produced from it are removed. Coverage for all four prompts drops to 3 of 4.",
    );
    expect(
      await screen.findByText("3 documents · 12 pages total"),
    ).toBeInTheDocument();
    expect(body).toEqual({
      document_id: "d0000000-0000-4000-8000-000000000004",
    });
    expect(onRemoved).toHaveBeenCalledWith(
      "d0000000-0000-4000-8000-000000000004",
      [
        "d0000000-0000-4000-8000-000000000001",
        "d0000000-0000-4000-8000-000000000002",
        "d0000000-0000-4000-8000-000000000003",
      ],
    );
  });

  it("cannot remove a document twice while its removal is in flight", async () => {
    serveList(promptDocumentFixtures.list);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const removed = vi.fn();
    mockApi(
      http.delete(FILE, async () => {
        removed();
        await new Promise(() => undefined);
        return HttpResponse.json("");
      }),
    );
    const { user } = renderPanel();
    const button = await screen.findByRole("button", {
      name: "Remove amex_jan_2026.pdf",
    });
    await user.click(button);
    await waitFor(() => expect(removed).toHaveBeenCalledTimes(1));
    expect(button).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Remove CreditCardStatement.pdf" }),
    ).toBeEnabled();
  });

  it("holds each row while its own removal is in flight, and never offers a document being removed", async () => {
    serveList(promptDocumentFixtures.list);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const answers = new Map<string, () => void>();
    mockApi(
      http.delete(FILE, async ({ request }) => {
        const { document_id } = (await request.json()) as {
          document_id: string;
        };
        await new Promise<void>((resolve) => answers.set(document_id, resolve));
        return HttpResponse.json("File deleted succesfully.");
      }),
    );
    const onRemoved = vi.fn();
    const { user } = renderPanel({ onRemoved });
    const [first, second] = promptDocumentFixtures.list;
    if (!first || !second) {
      throw new Error("fixture needs two documents");
    }
    const removeFirst = await screen.findByRole("button", {
      name: `Remove ${first.document_name}`,
    });
    const removeSecond = screen.getByRole("button", {
      name: `Remove ${second.document_name}`,
    });
    await user.click(removeFirst);
    await user.click(removeSecond);
    await waitFor(() => expect(answers.size).toBe(2));
    expect(removeFirst).toBeDisabled();
    expect(removeSecond).toBeDisabled();
    answers.get(first.document_id)?.();
    await waitFor(() => expect(onRemoved).toHaveBeenCalledTimes(1));
    expect(onRemoved.mock.calls[0]?.[1]).not.toContain(second.document_id);
  });

  it("removes nothing when the user cancels", async () => {
    serveList(promptDocumentFixtures.list);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const removed = vi.fn();
    mockApi(http.delete(FILE, removed));
    const { user } = renderPanel();
    await user.click(
      await screen.findByRole("button", { name: "Remove amex_jan_2026.pdf" }),
    );
    expect(removed).not.toHaveBeenCalled();
  });
});

it("renders the container's footer actions", async () => {
  serveList([]);
  renderPanel({ footerActions: <button type="button">Done</button> });
  expect(
    await screen.findByRole("button", { name: "Done" }),
  ).toBeInTheDocument();
});
