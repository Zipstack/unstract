/*
 * Fixtures for services/promptDocuments, shaped as the backend's
 * PromptStudioDocumentStatusSerializer renders `GET prompt-document/`. A
 * backend that sends only id, name and tool fails the list parse:
 * document_id, document_name, tool, size_bytes, page_count (null for rows
 * uploaded before sizes were recorded) and one index_status entry per LLM
 * profile of the tool.
 */

import type {
  DocumentContent,
  PromptDocument,
  UploadedDocument,
} from "@v1/services/promptDocuments";
import { apiPath, HttpResponse, http, type TestSession } from "@v1/test";

export const TOOL_ID = "6f1c2e4a-8b3d-4c5e-9f70-1a2b3c4d5e6f";
const DEFAULT_PROFILE = "0b7c9d1e-2f3a-4b5c-8d6e-7f8091a2b3c4";
const OTHER_PROFILE = "1c8d0e2f-3a4b-4c5d-9e6f-8091a2b3c4d5";

type IndexState = PromptDocument["index_status"][number]["status"];

/** One document with a default and a second profile. */
export function makeDocument(
  overrides: Partial<Omit<PromptDocument, "index_status">> & {
    status?: IndexState;
    reason?: string | null;
  } = {},
): PromptDocument {
  const { status = "indexed", reason = null, ...fields } = overrides;
  return {
    document_id: "d0000000-0000-4000-8000-000000000001",
    document_name: "CreditCardStatement.pdf",
    tool: TOOL_ID,
    size_bytes: 412 * 1024,
    page_count: 6,
    index_status: [
      {
        profile_manager: DEFAULT_PROFILE,
        is_default: true,
        status,
        failure_reason: status === "failed" ? reason : null,
      },
      {
        profile_manager: OTHER_PROFILE,
        is_default: false,
        status: "pending",
        failure_reason: null,
      },
    ],
    ...fields,
  };
}

/** Frame D04's four documents: three parsed, one pending, 14 pages. */
export const promptDocumentFixtures = {
  list: [
    makeDocument(),
    makeDocument({
      document_id: "d0000000-0000-4000-8000-000000000002",
      document_name: "boa_march_2026.pdf",
      size_bytes: 288 * 1024,
      page_count: 2,
    }),
    makeDocument({
      document_id: "d0000000-0000-4000-8000-000000000003",
      document_name: "chase_feb_2026.pdf",
      size_bytes: 611 * 1024,
      page_count: 4,
    }),
    makeDocument({
      document_id: "d0000000-0000-4000-8000-000000000004",
      document_name: "amex_jan_2026.pdf",
      size_bytes: 305 * 1024,
      page_count: 2,
      status: "pending",
    }),
  ],
  /** Frame D07's parse failure, with the extractor's reason. */
  failed: makeDocument({
    document_id: "d0000000-0000-4000-8000-000000000004",
    document_name: "amex_jan_2026.pdf",
    size_bytes: 305 * 1024,
    page_count: 2,
    status: "failed",
    reason: "LLM Whisperer V2 returned no text.",
  }),
} satisfies Record<string, PromptDocument | PromptDocument[]>;

/** `POST file/<tool>` as upload_for_ide answers it. */
export const uploadedFixture: UploadedDocument = {
  document_id: "d0000000-0000-4000-8000-000000000009",
  document_name: "new_statement.pdf",
  tool: TOOL_ID,
};

/** "%PDF-1.4" base64-encoded, as fetch_contents_ide sends a PDF. */
export const pdfContent: DocumentContent = {
  data: "JVBERi0xLjQ=",
  mime_type: "application/pdf",
};

/** Handlers for the prompt-document list, keyed by tool; records each URL. */
export const promptDocumentHandlers = (
  session: TestSession,
  rows: readonly unknown[] = promptDocumentFixtures.list,
  seen: URL[] = [],
) => [
  http.get(
    apiPath(session, "/prompt-studio/prompt-document/"),
    ({ request }) => {
      const url = new URL(request.url);
      seen.push(url);
      return HttpResponse.json(rows);
    },
  ),
];
