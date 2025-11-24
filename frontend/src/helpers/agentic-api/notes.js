import { agenticApiClient } from "./client";

export const notesApi = {
  /**
   * Create or update a note
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {Object} request - {field_path, note_text}
   * @return {Promise<Object>} Created/updated note
   */
  createOrUpdate: async (projectId, documentId, request) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/documents/${documentId}/notes`,
      request
    );
    return response.data;
  },

  /**
   * Get all notes for a document
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Array>} List of notes
   */
  list: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/notes`
    );
    return response.data;
  },

  /**
   * Get a specific note
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Note
   */
  get: async (projectId, documentId, fieldPath) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/notes/${encodeURIComponent(
        fieldPath
      )}`
    );
    return response.data;
  },

  /**
   * Delete a note
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Delete confirmation
   */
  delete: async (projectId, documentId, fieldPath) => {
    const response = await agenticApiClient.delete(
      `/projects/${projectId}/documents/${documentId}/notes/${encodeURIComponent(
        fieldPath
      )}`
    );
    return response.data;
  },
};
