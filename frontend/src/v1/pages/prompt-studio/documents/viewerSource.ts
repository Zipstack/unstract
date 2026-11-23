import type { DocumentSource } from "@v1/lib/pdf/types";
import type { DocumentContent } from "@v1/services/promptDocuments";

const TEXT_TYPES = new Set(["text/plain", "text/csv"]);

/**
 * What the viewer shows for stored contents: a PDF as bytes, text and CSV as
 * text, and null (no preview) for anything else, such as the notice the
 * backend sends for a spreadsheet.
 */
export function toViewerSource(
  content: DocumentContent,
): DocumentSource | null {
  if (content.mime_type === "application/pdf") {
    try {
      const binary = atob(content.data);
      return {
        kind: "data",
        data: Uint8Array.from(binary, (char) => char.charCodeAt(0)),
      };
    } catch {
      return null;
    }
  }
  if (TEXT_TYPES.has(content.mime_type)) {
    return { kind: "text", text: content.data };
  }
  return null;
}
