import { describe, expect, it } from "vitest";
import { toViewerSource } from "./viewerSource";

describe("toViewerSource", () => {
  it("decodes a base64 PDF into bytes for the viewer", () => {
    const source = toViewerSource({
      data: "JVBERi0xLjQ=",
      mime_type: "application/pdf",
    });
    expect(source?.kind).toBe("data");
    const bytes = source?.kind === "data" ? new Uint8Array(source.data) : null;
    expect(new TextDecoder().decode(bytes ?? undefined)).toBe("%PDF-1.4");
  });

  it("shows text and CSV as text", () => {
    expect(toViewerSource({ data: "a,b", mime_type: "text/csv" })).toEqual({
      kind: "text",
      text: "a,b",
    });
    expect(toViewerSource({ data: "hi", mime_type: "text/plain" })).toEqual({
      kind: "text",
      text: "hi",
    });
  });

  it("has no preview for any other type, such as a spreadsheet's notice", () => {
    expect(
      toViewerSource({
        data: "Preview not available for Excel files.",
        mime_type: "application/vnd.ms-excel",
      }),
    ).toBeNull();
  });

  it("passes an empty text file on, for the viewer's no-text state", () => {
    expect(toViewerSource({ data: "", mime_type: "text/plain" })).toEqual({
      kind: "text",
      text: "",
    });
  });

  it("has no preview for a PDF whose data is not base64", () => {
    expect(
      toViewerSource({ data: "%%% not base64", mime_type: "application/pdf" }),
    ).toBeNull();
  });
});
