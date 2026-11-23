import { queryOptions } from "@tanstack/react-query";
import type { AxiosProgressEvent } from "axios";
import { z } from "zod";
import { currentOrganizationId } from "./context";
import { http, orgPath, type RequestOptions } from "./http";

/*
 * A Prompt Studio project's documents: the list with size, pages and index
 * state per LLM profile, upload, delete, indexing and the stored contents.
 * Responses are parsed at this boundary, so a contract change fails here and
 * not deep inside a screen.
 */

export const INDEX_STATES = ["indexed", "pending", "failed"] as const;
export type IndexState = (typeof INDEX_STATES)[number];

/** A document's index state under one LLM profile of the tool. */
export const profileIndexStatusSchema = z.object({
  profile_manager: z.string(),
  is_default: z.boolean(),
  status: z.enum(INDEX_STATES),
  /** The extractor's error; null unless failed, or when the user may not see it. */
  failure_reason: z.string().nullable(),
});
export type ProfileIndexStatus = z.infer<typeof profileIndexStatusSchema>;

/** A row of `GET prompt-studio/prompt-document/?tool_id=`. */
export const promptDocumentSchema = z.object({
  document_id: z.string(),
  document_name: z.string(),
  tool: z.string(),
  /** Null for documents uploaded before sizes were recorded. */
  size_bytes: z.number().int().nonnegative().nullable(),
  /** Null when unknown: older uploads, or a file with no page count. */
  page_count: z.number().int().nonnegative().nullable(),
  index_status: z.array(profileIndexStatusSchema),
});
export type PromptDocument = z.infer<typeof promptDocumentSchema>;

const promptDocumentListSchema = z.array(promptDocumentSchema);

/** What upload_for_ide returns for each stored file. */
export const uploadedDocumentSchema = z.object({
  document_id: z.string(),
  document_name: z.string(),
  tool: z.string(),
});
export type UploadedDocument = z.infer<typeof uploadedDocumentSchema>;

const uploadResponseSchema = z.object({
  data: z.array(uploadedDocumentSchema).min(1),
});

export const DOCUMENT_VIEWS = ["ORIGINAL", "EXTRACT"] as const;
export type DocumentView = (typeof DOCUMENT_VIEWS)[number];

/** A PDF arrives base64-encoded; text and CSV as text; other types as a message. */
export const documentContentSchema = z.object({
  data: z.string(),
  mime_type: z.string(),
});
export type DocumentContent = z.infer<typeof documentContentSchema>;

export type DocumentRef = Readonly<{ toolId: string; documentId: string }>;
export type ContentParams = DocumentRef & Readonly<{ view: DocumentView }>;
export type UploadParams = Readonly<{
  toolId: string;
  file: File;
  /** Bytes sent so far, as the browser reports them. */
  onProgress?: (loaded: number) => void;
}>;

const filePath = (toolId: string) =>
  `/prompt-studio/file/${encodeURIComponent(toolId)}` as const;

/** `GET /api/v1/unstract/<org>/prompt-studio/prompt-document/?tool_id=`. */
export async function listPromptDocuments(
  toolId: string,
  { signal, org }: RequestOptions = {},
): Promise<PromptDocument[]> {
  const { data } = await http.get<unknown>(
    orgPath("/prompt-studio/prompt-document/", org),
    { params: { tool_id: toolId }, signal },
  );
  return promptDocumentListSchema.parse(data);
}

/** `POST prompt-studio/file/<tool>`: one file, multipart field `file`. */
export async function uploadPromptDocument(
  { toolId, file, onProgress }: UploadParams,
  { signal, org }: RequestOptions = {},
): Promise<UploadedDocument> {
  const body = new FormData();
  body.append("file", file);
  const { data } = await http.post<unknown>(
    orgPath(filePath(toolId), org),
    body,
    {
      signal,
      onUploadProgress: onProgress
        ? (event: AxiosProgressEvent) => onProgress(event.loaded)
        : undefined,
    },
  );
  const [document] = uploadResponseSchema.parse(data).data;
  return document as UploadedDocument;
}

/** `DELETE prompt-studio/file/<tool>`; outputs produced from it go with it. */
export async function deletePromptDocument(
  { toolId, documentId }: DocumentRef,
  { signal, org }: RequestOptions = {},
): Promise<void> {
  await http.delete(orgPath(filePath(toolId), org), {
    data: { document_id: documentId },
    signal,
  });
}

/** `POST prompt-studio/index-document/<tool>`; the result arrives later. */
export async function indexPromptDocument(
  { toolId, documentId }: DocumentRef,
  { signal, org }: RequestOptions = {},
): Promise<void> {
  await http.post(
    orgPath(`/prompt-studio/index-document/${encodeURIComponent(toolId)}`, org),
    { document_id: documentId },
    { signal },
  );
}

/** `GET prompt-studio/file/<tool>?document_id=&view_type=`. */
export async function fetchDocumentContent(
  { toolId, documentId, view }: ContentParams,
  { signal, org }: RequestOptions = {},
): Promise<DocumentContent> {
  const { data } = await http.get<unknown>(orgPath(filePath(toolId), org), {
    params: { document_id: documentId, view_type: view },
    signal,
  });
  return documentContentSchema.parse(data);
}

/** `PATCH prompt-studio/<tool>/` with `output`: the document prompts show. */
export async function selectToolDocument(
  { toolId, documentId }: DocumentRef,
  { signal, org }: RequestOptions = {},
): Promise<void> {
  await http.patch(
    orgPath(`/prompt-studio/${encodeURIComponent(toolId)}/`, org),
    { output: documentId },
    { signal },
  );
}

/** Query keys: `[org, "prompt-documents", "list" | "content", …]`. */
export const promptDocumentKeys = {
  all: () => [currentOrganizationId(), "prompt-documents"] as const,
  list: (toolId: string) =>
    [...promptDocumentKeys.all(), "list", toolId] as const,
  content: (params: ContentParams) =>
    [...promptDocumentKeys.all(), "content", params] as const,
};

// Each query fetches for the org in its key.
export const promptDocumentQueries = {
  list: (toolId: string) =>
    queryOptions({
      queryKey: promptDocumentKeys.list(toolId),
      queryFn: ({ queryKey: [org], signal }) =>
        listPromptDocuments(toolId, { signal, org }),
    }),
  content: (params: ContentParams) =>
    queryOptions({
      queryKey: promptDocumentKeys.content(params),
      queryFn: ({ queryKey: [org], signal }) =>
        fetchDocumentContent(params, { signal, org }),
      // Stored contents do not change; a re-index invalidates EXTRACT.
      staleTime: Number.POSITIVE_INFINITY,
    }),
};
