// Use the worker file from the public folder (served as static asset)
// This avoids Webpack processing which incorrectly bundles it with require() statements
// Note: The ?url import suffix only works in Vite, not in CRA (Webpack)
export const PDF_WORKER_URL = "/pdf.worker.min.js";
