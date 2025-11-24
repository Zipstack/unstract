import { agenticApiClient } from "./client";

export const documentsApi = {
  /**
   * List all documents in a project
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} List of documents
   */
  list: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/`
    );
    return response.data;
  },

  /**
   * Upload a document
   * @param {string} projectId - Project ID
   * @param {File} file - File to upload
   * @return {Promise<Object>} Uploaded document
   */
  upload: async (projectId, file) => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await agenticApiClient.post(
      `/projects/${projectId}/documents/upload/`,
      formData,
      {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      }
    );
    return response.data;
  },

  /**
   * Delete a document
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Delete confirmation
   */
  delete: async (projectId, documentId) => {
    const response = await agenticApiClient.delete(
      `/projects/${projectId}/documents/${documentId}`
    );
    return response.data;
  },

  /**
   * Process a single document
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Job ID
   */
  process: async (projectId, documentId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/documents/${documentId}/process`
    );
    return response.data;
  },

  /**
   * Get job status
   * @param {string} jobId - Job ID
   * @return {Promise<Object>} Job status
   */
  getJobStatus: async (jobId) => {
    const response = await agenticApiClient.get(`/jobs/${jobId}/`);
    return response.data;
  },

  /**
   * Get document status for all documents in a project
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} Document statuses
   */
  getDocumentStatus: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/status`
    );
    return response.data;
  },

  /**
   * Process batch of documents
   * @param {string} projectId - Project ID
   * @param {string} connectorId - Connector ID
   * @return {Promise<Object>} Batch process response
   */
  processBatch: async (projectId, connectorId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/documents/process-batch`,
      { connector_id: connectorId }
    );
    return response.data;
  },

  /**
   * Get document raw text
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Raw text
   */
  getDocumentRawText: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/raw-text/`
    );
    return response.data;
  },

  /**
   * Alias for compatibility - Get document raw text
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Raw text
   */
  getRawText: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/raw-text/`
    );
    return response.data;
  },

  /**
   * Process a document stage
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {Object} data - Data containing stage
   * @return {Promise<Object>} Processing result
   */
  processStage: async (projectId, documentId, data) => {
    const response = await agenticApiClient.post(
      `/documents/${documentId}/process_stage/`,
      data
    );
    return response.data;
  },

  /**
   * Get document summary
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Summary text
   */
  getDocumentSummary: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/summary/`
    );
    return response.data;
  },

  /**
   * Alias for getDocumentSummary
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Summary text
   */
  getSummary: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/summary/`
    );
    return response.data;
  },

  /**
   * Get document verified data
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Verified data
   */
  getDocumentVerifiedData: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/verified-data`
    );
    return response.data;
  },

  /**
   * Alias for getDocumentVerifiedData
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Verified data
   */
  getVerifiedData: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/verified-data`
    );
    return response.data;
  },

  /**
   * Get document extraction data
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Extraction data
   */
  getDocumentExtractionData: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/extraction-data/`
    );
    return response.data;
  },

  /**
   * Alias for getDocumentExtractionData
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Extraction data
   */
  getExtractionData: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/extraction-data/`
    );
    return response.data;
  },
};
