/**
 * Agentic Studio API Client
 *
 * This module provides a comprehensive API client for the Agentic Studio backend.
 * It includes all the necessary endpoints for managing projects, documents, prompts,
 * schema, extraction, processing, analytics, notes, and connectors.
 */

export {
  agenticApiClient,
  handleApiError,
  showApiError,
  showApiSuccess,
} from "./client";
export { projectsApi } from "./projects";
export { documentsApi } from "./documents";
export { promptsApi } from "./prompts";
export { schemaApi } from "./schema";
export { extractionApi } from "./extraction";
export { processingApi } from "./processing";
export { analyticsApi } from "./analytics";
export { notesApi } from "./notes";
export { connectorsApi } from "./connectors";
export * from "./types";
