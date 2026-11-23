/*
 * Builds small PDFs in memory for the document viewer's gallery and its
 * browser tests (UN-4645), so neither needs a binary fixture or a backend.
 * Each page carries its number and, optionally, filled rectangles at known
 * positions: a highlight placed at the same fractions must cover one exactly,
 * at any zoom.
 */

/** A filled rectangle, in fractions of the page box from the top-left. */
export interface SampleMark {
  x: number;
  y: number;
  w: number;
  h: number;
  /** Fill colour, each channel 0 to 255. */
  rgb: readonly [number, number, number];
}

export interface SamplePdfOptions {
  pages: number;
  /** Page size in PDF points; US Letter by default. */
  width?: number;
  height?: number;
  /** The rectangles drawn on a 0-based page. */
  marks?: (pageIndex: number) => readonly SampleMark[];
}

function num(value: number): string {
  return Number(value.toFixed(2)).toString();
}

function pageContent(
  index: number,
  width: number,
  height: number,
  marks: readonly SampleMark[],
): string {
  const ops: string[] = [
    "0 g",
    "BT /F1 24 Tf",
    `72 ${num(height - 72)} Td`,
    `(Page ${index + 1}) Tj`,
    "ET",
  ];
  for (const mark of marks) {
    const [r, g, b] = mark.rgb.map((channel) => num(channel / 255));
    // PDF space runs up from the bottom-left; the mark runs down from the top.
    const bottom = height - (mark.y + mark.h) * height;
    ops.push(
      `${r} ${g} ${b} rg`,
      `${num(mark.x * width)} ${num(bottom)} ${num(mark.w * width)} ${num(mark.h * height)} re f`,
    );
  }
  return ops.join("\n");
}

/** A valid PDF, as bytes, with `pages` numbered pages. */
export function samplePdf({
  pages,
  width = 612,
  height = 792,
  marks,
}: SamplePdfOptions): Uint8Array {
  // Objects 1-3 are the catalog, the page tree and the font; then each page
  // and its content stream, in pairs.
  const pageId = (index: number) => 4 + index * 2;
  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Count ${pages} /Kids [${Array.from(
      { length: pages },
      (_, index) => `${pageId(index)} 0 R`,
    ).join(" ")}] >>`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  for (let index = 0; index < pages; index++) {
    const stream = pageContent(index, width, height, marks?.(index) ?? []);
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width} ${height}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${pageId(index) + 1} 0 R >>`,
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    );
  }

  // Everything is ASCII, so string length is byte length.
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) {
    body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  }
  body += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new TextEncoder().encode(body);
}
