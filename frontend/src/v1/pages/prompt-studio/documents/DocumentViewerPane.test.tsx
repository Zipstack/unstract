import { screen, waitFor } from "@testing-library/react";
import type { DocumentViewerProps } from "@v1/components/patterns/document-viewer/DocumentViewer";
import { setOrganizationId } from "@v1/services/context";
import type { DocumentContent } from "@v1/services/promptDocuments";
import {
  apiPath,
  DEFAULT_SESSION,
  expectNoA11yViolations,
  HttpResponse,
  http,
  mockApi,
  renderV1,
} from "@v1/test";
import {
  makeDocument,
  pdfContent,
  promptDocumentFixtures,
  TOOL_ID,
} from "@v1/test/fixtures/promptDocuments";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  DocumentViewerPane,
  type DocumentViewerPaneProps,
} from "./DocumentViewerPane";

// The document viewer pattern is tested on its own; here it only reports what it got.
vi.mock("@v1/components/patterns/document-viewer/DocumentViewer", () => ({
  DocumentViewer: ({ source, highlights }: DocumentViewerProps) => (
    <div data-testid="viewer">
      {source?.kind === "text" ? source.text : source?.kind}
      {highlights ? ` · ${highlights.length} highlights` : ""}
    </div>
  ),
}));

const ORG = DEFAULT_SESSION;
const FIRST = makeDocument();
const TEXT: DocumentContent = {
  data: "Statement text",
  mime_type: "text/plain",
};

beforeEach(() => setOrganizationId(ORG.organization.id));
afterEach(() => setOrganizationId(null));

/** Serves the list and the two views; a view set to a number answers that status. */
function serve(
  views: Partial<Record<"ORIGINAL" | "EXTRACT", DocumentContent | number>>,
  rows = promptDocumentFixtures.list,
) {
  const seen: string[] = [];
  mockApi(
    http.get(apiPath(ORG, "/prompt-studio/prompt-document/"), () =>
      HttpResponse.json(rows),
    ),
    http.get(apiPath(ORG, `/prompt-studio/file/${TOOL_ID}`), ({ request }) => {
      const url = new URL(request.url);
      const view = url.searchParams.get("view_type") as "ORIGINAL" | "EXTRACT";
      seen.push(`${url.searchParams.get("document_id")}:${view}`);
      const answer = views[view];
      return typeof answer === "number" || answer === undefined
        ? HttpResponse.json(
            {
              type: "client_error",
              errors: [{ code: "x", detail: "Nope.", attr: null }],
            },
            { status: typeof answer === "number" ? answer : 500 },
          )
        : HttpResponse.json(answer);
    }),
  );
  return seen;
}

function renderPane(props: Partial<DocumentViewerPaneProps> = {}) {
  return renderV1(
    <DocumentViewerPane
      toolId={TOOL_ID}
      selectedId={FIRST.document_id}
      onSelect={() => undefined}
      onManageDocuments={() => undefined}
      {...props}
    />,
  );
}

it("shows the selected document's PDF with pages · size · state (C10)", async () => {
  const seen = serve({ ORIGINAL: pdfContent });
  renderPane();
  expect(await screen.findByTestId("viewer")).toHaveTextContent("data");
  expect(screen.getByText("1 of 4")).toBeInTheDocument();
  expect(screen.getByText("6 pages · 412 KB · parsed")).toBeInTheDocument();
  expect(seen).toEqual([`${FIRST.document_id}:ORIGINAL`]);
});

it("lists every document in the switcher and picks one (C10)", async () => {
  serve({ ORIGINAL: pdfContent });
  const onSelect = vi.fn();
  const { user } = renderPane({ onSelect });
  await user.click(
    await screen.findByRole("button", {
      name: "Document: CreditCardStatement.pdf",
    }),
  );
  const amex = await screen.findByRole("menuitemradio", {
    name: /amex_jan_2026\.pdf/,
  });
  expect(amex).toHaveAccessibleDescription("2 pages · 305 KB · pending");
  expect(
    screen.getByRole("menuitemradio", { name: /CreditCardStatement\.pdf/ }),
  ).toHaveAttribute("aria-checked", "true");
  await user.click(amex);
  expect(onSelect).toHaveBeenCalledWith("d0000000-0000-4000-8000-000000000004");
});

it("does not report the shown document as a new choice", async () => {
  serve({ ORIGINAL: pdfContent });
  const onSelect = vi.fn();
  const { user } = renderPane({ onSelect });
  await user.click(
    await screen.findByRole("button", {
      name: "Document: CreditCardStatement.pdf",
    }),
  );
  await user.click(
    await screen.findByRole("menuitemradio", {
      name: /CreditCardStatement\.pdf/,
    }),
  );
  expect(onSelect).not.toHaveBeenCalled();
});

it("shows the extracted text in Raw View", async () => {
  const seen = serve({ ORIGINAL: pdfContent, EXTRACT: TEXT });
  const { user } = renderPane();
  await screen.findByTestId("viewer");
  await user.click(screen.getByRole("tab", { name: "Raw View" }));
  await waitFor(() =>
    expect(screen.getByTestId("viewer")).toHaveTextContent("Statement text"),
  );
  expect(seen).toContain(`${FIRST.document_id}:EXTRACT`);
});

it("says to index when there is no extracted text yet", async () => {
  serve({ ORIGINAL: pdfContent, EXTRACT: 404 });
  const { user } = renderPane();
  await user.click(await screen.findByRole("tab", { name: "Raw View" }));
  expect(
    await screen.findByText(
      "Raw content is not available. Index the document to generate it.",
    ),
  ).toBeInTheDocument();
});

it.each([
  [
    "the file has no preview",
    { data: "Preview not available.", mime_type: "application/vnd.ms-excel" },
  ],
  ["the PDF data is not base64", { data: "%%%", mime_type: "application/pdf" }],
] as const)("shows failed to load when %s (C14)", async (_, original) => {
  serve({ ORIGINAL: original, EXTRACT: TEXT });
  const { user, container } = renderPane();
  expect(
    await screen.findByText("Failed to load the document"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "The file is stored but the viewer could not render it. Prompts still run against the parsed text.",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("412 KB · preview unavailable")).toBeInTheDocument();
  await expectNoA11yViolations(container);
  await user.click(screen.getByRole("button", { name: "Open Raw View" }));
  await waitFor(() =>
    expect(screen.getByTestId("viewer")).toHaveTextContent("Statement text"),
  );
});

it("shows the request's error, not C14, when the file cannot be fetched", async () => {
  const seen = serve({ ORIGINAL: 500 });
  const { user } = renderPane();
  expect(await screen.findByText("Nope.")).toBeInTheDocument();
  expect(
    screen.queryByText("Failed to load the document"),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(seen).toHaveLength(2));
});

it("fetches the file again on Retry (C14)", async () => {
  const seen = serve({
    ORIGINAL: { data: "Preview not available.", mime_type: "text/x-unknown" },
  });
  const { user } = renderPane();
  await user.click(await screen.findByRole("button", { name: "Retry" }));
  await waitFor(() => expect(seen).toHaveLength(2));
});

it("asks for a choice when the saved document is not in the list", async () => {
  serve({ ORIGINAL: pdfContent });
  renderPane({ selectedId: "removed-elsewhere" });
  expect(
    await screen.findByText("Choose a document to preview"),
  ).toBeInTheDocument();
  expect(screen.queryByText("Nothing to preview yet")).not.toBeInTheDocument();
});

it("has nothing to preview with no documents (D05)", async () => {
  serve({}, []);
  renderPane({ selectedId: null });
  expect(await screen.findByText("Nothing to preview yet")).toBeInTheDocument();
  expect(screen.getByText("No document selected")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Choose a document" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Choose a document" }),
  ).toHaveTextContent("No documents");
});

it("opens Manage Documents", async () => {
  serve({ ORIGINAL: pdfContent });
  const onManageDocuments = vi.fn();
  const { user } = renderPane({ onManageDocuments });
  await user.click(
    await screen.findByRole("button", { name: "Manage Documents" }),
  );
  expect(onManageDocuments).toHaveBeenCalledTimes(1);
});

it("passes the highlight slot to the viewer and shows the tab accessory", async () => {
  serve({ ORIGINAL: pdfContent });
  renderPane({
    highlights: [{ id: "h1", page: 0, rect: [0, 0, 1, 1] }] as never,
    tabAccessory: <span>Confidence Score: NA</span>,
  });
  expect(await screen.findByTestId("viewer")).toHaveTextContent("1 highlights");
  expect(screen.getByText("Confidence Score: NA")).toBeInTheDocument();
});

it("shows processing while the workspace indexes the shown document", async () => {
  serve({ ORIGINAL: pdfContent });
  renderPane({ indexingIds: new Set([FIRST.document_id]) });
  expect(
    await screen.findByText("6 pages · 412 KB · processing"),
  ).toBeInTheDocument();
});

it("shows the list's error with Retry instead of an empty project", async () => {
  mockApi(
    http.get(apiPath(ORG, "/prompt-studio/prompt-document/"), () =>
      HttpResponse.json(
        {
          type: "server_error",
          errors: [{ code: "error", detail: "Server error.", attr: null }],
        },
        { status: 500 },
      ),
    ),
  );
  renderPane({ selectedId: null });
  expect(
    await screen.findByRole("button", { name: "Retry" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Nothing to preview yet")).not.toBeInTheDocument();
});

it("holds the switcher while a run uses the shown document", async () => {
  serve({ ORIGINAL: pdfContent });
  renderPane({ switchingDisabled: true });
  expect(
    await screen.findByRole("button", {
      name: `Document: ${FIRST.document_name}`,
    }),
  ).toBeDisabled();
});
