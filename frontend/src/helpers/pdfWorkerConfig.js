// Load the worker file from the installed pdfjs-dist package
// The ?url suffix tells Webpack 5 to return the URL of the asset
import pdfjsWorker from "pdfjs-dist/build/pdf.worker.min.js?url";

export const PDF_WORKER_URL = pdfjsWorker;
