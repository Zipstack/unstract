import { agenticApiClient } from "./client";

export const processingApi = {
  /**
   * Get processing status for a document stage
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {string} stage - Stage name (raw-text, summary, verified-data, extraction)
   * @return {Promise<Object>} Processing status
   */
  getProcessingStatus: async (projectId, documentId, stage) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/processing/documents/${documentId}/status/${stage}`
    );
    return response.data;
  },

  /**
   * Start processing for a document stage
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {string} stage - Stage name
   * @param {Object} config - Configuration {connector_id?}
   * @return {Promise<Object>} Processing initiation response
   */
  startProcessing: async (projectId, documentId, stage, config = {}) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/processing/documents/${documentId}/${stage}`,
      config
    );
    return response.data;
  },

  /**
   * Delete a processing stage
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {string} stage - Stage name
   * @return {Promise<Object>} Delete response
   */
  deleteStage: async (projectId, documentId, stage) => {
    const response = await agenticApiClient.delete(
      `/projects/${projectId}/processing/documents/${documentId}/${stage}`
    );
    return response.data;
  },

  /**
   * Get overall project processing state
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Project processing state
   */
  getProjectProcessingState: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/processing/state`
    );
    return response.data;
  },

  /**
   * Get processing state for all documents (polls Redis state for async tasks)
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Processing state with documents array
   */
  getProcessingState: async (projectId) => {
    const response = await agenticApiClient.get(
      `/documents/processing/state?project_id=${projectId}`
    );
    return response.data;
  },

  /**
   * Subscribe to Server-Sent Events for real-time processing updates
   * @param {string} projectId - Project ID
   * @param {Function} onMessage - Callback for SSE messages
   * @param {Function} onError - Callback for errors
   * @return {EventSource} EventSource instance
   */
  subscribeToSSE: (projectId, onMessage, onError) => {
    const eventSource = new EventSource(
      `${agenticApiClient.defaults.baseURL}/projects/${projectId}/processing/sse`,
      { withCredentials: true }
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error("Error parsing SSE message:", error);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE error:", error);
      if (onError) {
        onError(error);
      }
    };

    return eventSource;
  },

  /**
   * Get delete fields
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {Array<string>} fieldPaths - Array of field paths to delete
   * @return {Promise<Object>} Delete response
   */
  deleteFields: async (projectId, documentId, fieldPaths) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/documents/${documentId}/delete-fields`,
      { field_paths: fieldPaths }
    );
    return response.data;
  },
};
