import {
  apiPath,
  DEFAULT_SESSION,
  HttpResponse,
  http,
  mockApi,
} from "@v1/test";
import {
  makeDocument,
  pdfContent,
  promptDocumentFixtures,
  promptDocumentHandlers,
  TOOL_ID,
  uploadedFixture,
} from "@v1/test/fixtures/promptDocuments";
import { afterEach, beforeEach, expect, it } from "vitest";
import { setOrganizationId } from "./context";
import {
  deletePromptDocument,
  fetchDocumentContent,
  indexPromptDocument,
  listPromptDocuments,
  promptDocumentKeys,
  promptDocumentSchema,
  selectToolDocument,
  uploadPromptDocument,
} from "./promptDocuments";

const ORG = DEFAULT_SESSION;
const filePath = `/prompt-studio/file/${TOOL_ID}` as const;

beforeEach(() => setOrganizationId(ORG.organization.id));
afterEach(() => setOrganizationId(null));

it("lists a tool's documents with size, pages and index status", async () => {
  const seen: URL[] = [];
  mockApi(...promptDocumentHandlers(ORG, promptDocumentFixtures.list, seen));
  const rows = await listPromptDocuments(TOOL_ID);
  expect(rows).toEqual(promptDocumentFixtures.list);
  expect(seen[0]?.pathname).toBe(
    "/api/v1/unstract/org-1/prompt-studio/prompt-document/",
  );
  expect(seen[0]?.searchParams.get("tool_id")).toBe(TOOL_ID);
});

it("accepts rows uploaded before sizes and pages were recorded", () => {
  const legacy = makeDocument({ size_bytes: null, page_count: null });
  expect(promptDocumentSchema.parse(legacy)).toEqual(legacy);
});

it("rejects a list that breaks the contract instead of rendering it", async () => {
  const { index_status: _dropped, ...withoutStatus } = makeDocument();
  mockApi(...promptDocumentHandlers(ORG, [withoutStatus]));
  await expect(listPromptDocuments(TOOL_ID)).rejects.toThrow();
});

it("rejects an index state the contract does not name", () => {
  const row = makeDocument();
  const bad = {
    ...row,
    index_status: [{ ...row.index_status[0], status: "running" }],
  };
  expect(promptDocumentSchema.safeParse(bad).success).toBe(false);
});

it("uploads one file as the multipart field `file` and returns its row", async () => {
  let field: FormDataEntryValue | null = null;
  mockApi(
    http.post(apiPath(ORG, filePath), async ({ request }) => {
      field = (await request.formData()).get("file");
      return HttpResponse.json({ data: [uploadedFixture] });
    }),
  );
  const file = new File(["%PDF-1.4"], "new_statement.pdf", {
    type: "application/pdf",
  });
  const row = await uploadPromptDocument({ toolId: TOOL_ID, file });
  expect(row).toEqual(uploadedFixture);
  expect(field).toBeInstanceOf(File);
  expect((field as unknown as File).name).toBe("new_statement.pdf");
});

it("fails an upload whose answer holds no document", async () => {
  mockApi(
    http.post(apiPath(ORG, filePath), () => HttpResponse.json({ data: [] })),
  );
  const file = new File(["x"], "a.pdf", { type: "application/pdf" });
  await expect(
    uploadPromptDocument({ toolId: TOOL_ID, file }),
  ).rejects.toThrow();
});

it("deletes a document by id in the request body", async () => {
  let body: unknown = null;
  mockApi(
    http.delete(apiPath(ORG, filePath), async ({ request }) => {
      body = await request.json();
      return HttpResponse.json("File deleted succesfully.");
    }),
  );
  await deletePromptDocument({ toolId: TOOL_ID, documentId: "doc-1" });
  expect(body).toEqual({ document_id: "doc-1" });
});

it("starts indexing a document", async () => {
  let body: unknown = null;
  mockApi(
    http.post(
      apiPath(ORG, `/prompt-studio/index-document/${TOOL_ID}`),
      async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { task_id: "t", run_id: "r", status: "accepted" },
          { status: 202 },
        );
      },
    ),
  );
  await indexPromptDocument({ toolId: TOOL_ID, documentId: "doc-1" });
  expect(body).toEqual({ document_id: "doc-1" });
});

it("fetches a document's original or extracted contents", async () => {
  const seen: URL[] = [];
  mockApi(
    http.get(apiPath(ORG, filePath), ({ request }) => {
      seen.push(new URL(request.url));
      return HttpResponse.json(pdfContent);
    }),
  );
  const content = await fetchDocumentContent({
    toolId: TOOL_ID,
    documentId: "doc-1",
    view: "ORIGINAL",
  });
  expect(content).toEqual(pdfContent);
  expect(Object.fromEntries(seen[0]?.searchParams ?? [])).toEqual({
    document_id: "doc-1",
    view_type: "ORIGINAL",
  });
});

it("makes a document the tool's selected document", async () => {
  let body: unknown = null;
  mockApi(
    http.patch(
      apiPath(ORG, `/prompt-studio/${TOOL_ID}/`),
      async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ tool_id: TOOL_ID, output: "doc-2" });
      },
    ),
  );
  await selectToolDocument({ toolId: TOOL_ID, documentId: "doc-2" });
  expect(body).toEqual({ output: "doc-2" });
});

it("keys lists and contents by organisation and tool", () => {
  expect(promptDocumentKeys.list(TOOL_ID)).toEqual([
    "org-1",
    "prompt-documents",
    "list",
    TOOL_ID,
  ]);
  expect(
    promptDocumentKeys.content({
      toolId: TOOL_ID,
      documentId: "doc-1",
      view: "EXTRACT",
    }),
  ).toEqual([
    "org-1",
    "prompt-documents",
    "content",
    { toolId: TOOL_ID, documentId: "doc-1", view: "EXTRACT" },
  ]);
});
