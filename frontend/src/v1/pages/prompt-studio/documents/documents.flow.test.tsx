import { screen, waitFor, within } from "@testing-library/react";
import type { DocumentViewerProps } from "@v1/components/patterns/document-viewer/DocumentViewer";
import { setOrganizationId } from "@v1/services/context";
import type { PromptDocument } from "@v1/services/promptDocuments";
import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
  renderV1,
} from "@v1/test";
import {
  makeDocument,
  promptDocumentFixtures,
  TOOL_ID,
  uploadedFixture,
} from "@v1/test/fixtures/promptDocuments";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentsPanel } from "./DocumentsPanel";
import { DocumentViewerPane } from "./DocumentViewerPane";
import { useDocumentSelection } from "./useDocumentSelection";

/*
 * The spec's E2E flow (upload, switch, delete) at component level, with the
 * pane, the panel and the selection wired as the workspace frame will wire
 * them. The Playwright spec follows once the frame registers the page.
 */

vi.mock("@v1/components/patterns/document-viewer/DocumentViewer", () => ({
  DocumentViewer: ({ source }: DocumentViewerProps) => (
    <div data-testid="viewer">
      {source?.kind === "text" ? source.text : source?.kind}
    </div>
  ),
}));

const ORG = DEFAULT_SESSION;
const [FIRST, SECOND] = promptDocumentFixtures.list;

beforeEach(() => setOrganizationId(ORG.organization.id));
afterEach(() => setOrganizationId(null));

function Workspace() {
  const selection = useDocumentSelection(TOOL_ID, FIRST?.document_id ?? null);
  return (
    <>
      <DocumentViewerPane
        toolId={TOOL_ID}
        selectedId={selection.selectedId}
        onSelect={selection.select}
        onManageDocuments={() => undefined}
      />
      <DocumentsPanel
        toolId={TOOL_ID}
        onView={selection.select}
        onRemoved={selection.removed}
      />
    </>
  );
}

/** A small backend: the list, uploads, deletes, contents and the tool's saved document. */
function serveBackend(initial: readonly PromptDocument[]) {
  let rows = initial;
  const saved: string[] = [];
  const file = apiPath(ORG, `/prompt-studio/file/${TOOL_ID}`);
  mockApi(
    http.get(apiPath(ORG, "/prompt-studio/prompt-document/"), () =>
      HttpResponse.json(rows),
    ),
    http.get(file, ({ request }) => {
      const id = new URL(request.url).searchParams.get("document_id");
      return HttpResponse.json({
        data: `text of ${id}`,
        mime_type: "text/plain",
      });
    }),
    http.post(file, () => {
      rows = [
        ...rows,
        makeDocument({
          document_id: uploadedFixture.document_id,
          document_name: uploadedFixture.document_name,
          status: "pending",
        }),
      ];
      return HttpResponse.json({ data: [uploadedFixture] });
    }),
    http.delete(file, async ({ request }) => {
      const { document_id } = (await request.json()) as { document_id: string };
      rows = rows.filter((row) => row.document_id !== document_id);
      return HttpResponse.json("File deleted succesfully.");
    }),
    http.patch(
      apiPath(ORG, `/prompt-studio/${TOOL_ID}/`),
      async ({ request }) => {
        saved.push(((await request.json()) as { output: string }).output);
        return HttpResponse.json({});
      },
    ),
  );
  return saved;
}

it("uploads a document, switches documents and removes one", async () => {
  if (!FIRST || !SECOND) {
    throw new Error("fixture needs two documents");
  }
  const saved = serveBackend(promptDocumentFixtures.list.slice(0, 2));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const { user } = renderV1(<Workspace />);
  const viewer = await screen.findByTestId("viewer");
  await waitFor(() =>
    expect(viewer).toHaveTextContent(`text of ${FIRST.document_id}`),
  );

  // Upload: the new document joins the list and the switcher.
  await user.upload(
    screen.getByTestId("file-drop-input"),
    new File(["%PDF-1.4"], "new_statement.pdf", { type: "application/pdf" }),
  );
  expect(
    await screen.findByText("3 documents · 14 pages total"),
  ).toBeInTheDocument();
  expect(screen.getByText("1 of 3")).toBeInTheDocument();

  // Switch: the viewer shows the chosen document, and the tool saves it.
  await user.click(
    screen.getByRole("button", { name: `Document: ${FIRST.document_name}` }),
  );
  await user.click(
    await screen.findByRole("menuitemradio", {
      name: new RegExp(SECOND.document_name),
    }),
  );
  await waitFor(() =>
    expect(screen.getByTestId("viewer")).toHaveTextContent(
      `text of ${SECOND.document_id}`,
    ),
  );
  expect(screen.getByText("2 of 3")).toBeInTheDocument();

  // Remove the shown document: the viewer moves to the first one left.
  const list = screen.getByRole("list", { name: "Documents" });
  await user.click(
    within(list).getByRole("button", {
      name: `Remove ${SECOND.document_name}`,
    }),
  );
  expect(
    await screen.findByText("2 documents · 12 pages total"),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.getByTestId("viewer")).toHaveTextContent(
      `text of ${FIRST.document_id}`,
    ),
  );
  expect(saved).toEqual([SECOND.document_id, FIRST.document_id]);
});
