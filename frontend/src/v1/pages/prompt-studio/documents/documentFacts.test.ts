import {
  makeDocument,
  promptDocumentFixtures,
} from "@v1/test/fixtures/promptDocuments";
import { describe, expect, it } from "vitest";
import {
  documentState,
  failureReason,
  footerSummary,
  formatBytes,
  rowMeta,
  switcherMeta,
  unavailableMeta,
} from "./documentFacts";

const NONE = new Set<string>();

describe("formatBytes", () => {
  it.each([
    [0, "0 B"],
    [900, "900 B"],
    [1024, "1 KB"],
    [412 * 1024, "412 KB"],
    [1024 * 1024, "1 MB"],
    [1.25 * 1024 * 1024, "1.3 MB"],
    [200 * 1024 * 1024, "200 MB"],
  ])("%d bytes reads %s", (bytes, text) => {
    expect(formatBytes(bytes)).toBe(text);
  });
});

describe("documentState", () => {
  it("reads the default profile's state", () => {
    expect(documentState(makeDocument(), NONE)).toBe("parsed");
    expect(documentState(makeDocument({ status: "pending" }), NONE)).toBe(
      "pending",
    );
    expect(documentState(promptDocumentFixtures.failed, NONE)).toBe("failed");
  });

  it("ignores profiles other than the default", () => {
    const doc = makeDocument();
    const flipped = {
      ...doc,
      index_status: doc.index_status.map((entry) => ({
        ...entry,
        status: entry.is_default ? ("indexed" as const) : ("failed" as const),
      })),
    };
    expect(documentState(flipped, NONE)).toBe("parsed");
  });

  it("is pending when the tool has no default profile", () => {
    const doc = { ...makeDocument(), index_status: [] };
    expect(documentState(doc, NONE)).toBe("pending");
  });

  it("is processing while it is being indexed, whatever it was", () => {
    const doc = promptDocumentFixtures.failed;
    expect(documentState(doc, new Set([doc.document_id]))).toBe("processing");
  });
});

it("gives the default profile's failure reason only for a failed document", () => {
  expect(failureReason(promptDocumentFixtures.failed)).toBe(
    "LLM Whisperer V2 returned no text.",
  );
  expect(failureReason(makeDocument())).toBeNull();
});

describe("row and switcher lines", () => {
  const doc = makeDocument();

  it("reads size then pages in the list (D04)", () => {
    expect(rowMeta(doc, "parsed")).toBe("412 KB · 6 pages");
    expect(rowMeta(makeDocument({ page_count: 1 }), "parsed")).toBe(
      "412 KB · 1 page",
    );
  });

  it("reads 0 pages parsed for a failed document (D07)", () => {
    expect(rowMeta(promptDocumentFixtures.failed, "failed")).toBe(
      "305 KB · 0 pages parsed",
    );
  });

  it("leaves out what the backend does not know", () => {
    expect(rowMeta(makeDocument({ size_bytes: null }), "parsed")).toBe(
      "6 pages",
    );
    expect(
      rowMeta(makeDocument({ size_bytes: null, page_count: null }), "pending"),
    ).toBe("");
  });

  it("reads pages, size and state in the switcher (C10)", () => {
    expect(switcherMeta(doc, "parsed")).toBe("6 pages · 412 KB · parsed");
    expect(switcherMeta(makeDocument({ status: "pending" }), "pending")).toBe(
      "6 pages · 412 KB · pending",
    );
    expect(switcherMeta(makeDocument({ page_count: null }), "parsed")).toBe(
      "412 KB · parsed",
    );
  });

  it("reads size and preview unavailable when the viewer cannot render (C14)", () => {
    expect(unavailableMeta(doc)).toBe("412 KB · preview unavailable");
    expect(unavailableMeta(makeDocument({ size_bytes: null }))).toBe(
      "preview unavailable",
    );
  });
});

describe("footerSummary", () => {
  it("counts documents and pages (D04)", () => {
    expect(footerSummary(promptDocumentFixtures.list, NONE, 0)).toBe(
      "4 documents · 14 pages total",
    );
  });

  it("reads 0 documents when empty (D05)", () => {
    expect(footerSummary([], NONE, 0)).toBe("0 documents");
  });

  it("puts uploads first and drops the page total while uploading (D06)", () => {
    const two = promptDocumentFixtures.list.slice(0, 2);
    expect(footerSummary(two, NONE, 1)).toBe("1 uploading · 2 documents");
  });

  it("counts failed documents apart (D07)", () => {
    const rows = [promptDocumentFixtures.failed, makeDocument()];
    expect(footerSummary(rows, NONE, 0)).toBe("1 failed · 1 document");
  });

  it("drops the page total when a page count is unknown", () => {
    const rows = [makeDocument(), makeDocument({ page_count: null })];
    expect(footerSummary(rows, NONE, 0)).toBe("2 documents");
  });

  it("counts a failed document being re-indexed as a document", () => {
    const failed = promptDocumentFixtures.failed;
    expect(footerSummary([failed], new Set([failed.document_id]), 0)).toBe(
      "1 document · 2 pages total",
    );
  });
});
