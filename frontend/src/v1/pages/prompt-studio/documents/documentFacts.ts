import type { PromptDocument } from "@v1/services/promptDocuments";

/** What a document shows: its default profile's index state, or processing while it indexes. */
export type DocumentState = "parsed" | "pending" | "processing" | "failed";

const SEP = " · ";
const KB = 1024;
const MB = 1024 * KB;

/** "900 B", "412 KB", "1.3 MB", "200 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < KB) {
    return `${bytes} B`;
  }
  if (bytes < MB) {
    return `${Math.round(bytes / KB)} KB`;
  }
  return `${Number((bytes / MB).toFixed(1))} MB`;
}

export function countLabel(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The document's entry for the tool's default LLM profile, if it has one. */
export function defaultIndexStatus(document: PromptDocument) {
  return document.index_status.find((entry) => entry.is_default);
}

/**
 * The state of `document` under the tool's default LLM profile. `indexing`
 * holds the ids being indexed now; with no default profile it is pending.
 */
export function documentState(
  document: PromptDocument,
  indexing: ReadonlySet<string>,
): DocumentState {
  if (indexing.has(document.document_id)) {
    return "processing";
  }
  switch (defaultIndexStatus(document)?.status) {
    case "indexed":
      return "parsed";
    case "failed":
      return "failed";
    default:
      return "pending";
  }
}

/** The extractor's reason for a failed document, when the backend shares it. */
export function failureReason(document: PromptDocument): string | null {
  const status = defaultIndexStatus(document);
  return status?.status === "failed" ? status.failure_reason : null;
}

const size = (document: PromptDocument) =>
  document.size_bytes === null ? null : formatBytes(document.size_bytes);
const pages = (document: PromptDocument) =>
  document.page_count === null ? null : countLabel(document.page_count, "page");
const join = (parts: readonly (string | null)[]) =>
  parts.filter((part): part is string => part !== null).join(SEP);

/** The list row's second line: "412 KB · 6 pages"; a failure parsed nothing. */
export function rowMeta(
  document: PromptDocument,
  state: DocumentState,
): string {
  return join([
    size(document),
    state === "failed" ? "0 pages parsed" : pages(document),
  ]);
}

/** The switcher row's second line: "6 pages · 412 KB · parsed". */
export function switcherMeta(
  document: PromptDocument,
  state: DocumentState,
): string {
  return join([pages(document), size(document), state]);
}

/** The viewer footer when the file cannot be rendered: "412 KB · preview unavailable". */
export function unavailableMeta(document: PromptDocument): string {
  return join([size(document), "preview unavailable"]);
}

/**
 * The Documents footer: "1 uploading · 1 failed · 2 documents", with
 * "· 14 pages total" only when nothing is uploading or failed and every page
 * count is known (frames D04 to D07).
 */
export function footerSummary(
  documents: readonly PromptDocument[],
  indexing: ReadonlySet<string>,
  uploading: number,
): string {
  const failed = documents.filter(
    (document) => documentState(document, indexing) === "failed",
  ).length;
  const counted = documents.filter(
    (document) => documentState(document, indexing) !== "failed",
  );
  const parts = [
    uploading > 0 ? `${uploading} uploading` : null,
    failed > 0 ? `${failed} failed` : null,
    countLabel(counted.length, "document"),
  ];
  const pageCounts = counted.map((document) => document.page_count);
  if (
    uploading === 0 &&
    failed === 0 &&
    counted.length > 0 &&
    pageCounts.every((count) => count !== null)
  ) {
    const total = pageCounts.reduce<number>(
      (sum, count) => sum + (count ?? 0),
      0,
    );
    parts.push(`${countLabel(total, "page")} total`);
  }
  return join(parts);
}
