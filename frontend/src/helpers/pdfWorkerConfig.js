// Webpack 5 / Vite compatible asset module
// Works with both CRA (Webpack) and Vite bundlers
export const PDF_WORKER_URL = new URL(
  "pdfjs-dist/build/pdf.worker.min.js",
  import.meta.url
).toString();
