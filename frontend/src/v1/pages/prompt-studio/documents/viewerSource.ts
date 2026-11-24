import type { DocumentSource } from "@v1/lib/pdf/types";
import type { DocumentContent } from "@v1/services/promptDocuments";

const TEXT_TYPES = new Set(["text/plain", "text/csv"]);

/**
 * What the viewer shows for stored contents: a PDF as bytes, text and CSV as
 * text, and null (no preview) for anything else, such as the notice the
 * backend sends for a spreadsheet or empty data.
 */
export function toViewerSource(
  content: DocumentContent,
): DocumentSource | null {
  if (content.mime_type === "application/pdf") {
    try {
      const binary = atob(content.data);
      // A plain loop: a per-byte callback is slow on a 200 MB file.
      const data = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        data[index] = binary.charCodeAt(index);
      }
      return { kind: "data", data };
    } catch {
      return null;
    }
  }
  // The backend sends empty data for a type it does not read.
  if (TEXT_TYPES.has(content.mime_type) && content.data !== "") {
    return { kind: "text", text: content.data };
  }
  return null;
}
