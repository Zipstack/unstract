// Load the worker file from the installed pdfjs-dist package
// The ?url suffix tells Webpack 5 to return the URL of the asset
// eslint-disable-next-line import/no-unresolved
export { default as PDF_WORKER_URL } from "pdfjs-dist/build/pdf.worker.min.js?url";
