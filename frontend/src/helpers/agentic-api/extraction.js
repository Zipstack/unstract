import { agenticApiClient } from "./client";

export const extractionApi = {
  /**
   * Run provisional extraction
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Extracted data
   */
  runProvisional: async (projectId, documentId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/extract/provisional/${documentId}/`
    );
    return response.data;
  },

  /**
   * Save verified data
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @param {Object} data - Data to save
   * @return {Promise<Object>} Saved verified data
   */
  saveVerifiedData: async (projectId, documentId, data) => {
    const response = await agenticApiClient.put(
      `/projects/${projectId}/extract/verified/${documentId}/`,
      { data }
    );
    return response.data;
  },

  /**
   * Get all verified data for a project
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} List of verified data
   */
  getAllVerifiedData: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/extract/verified/`
    );
    return response.data;
  },

  /**
   * Get verified data for a document
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Verified data
   */
  getVerifiedData: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/extract/verified/${documentId}/`
    );
    return response.data;
  },

  /**
   * Generate verified data using LLM
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Generated verified data
   */
  generateVerifiedData: async (projectId, documentId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/extract/verified/${documentId}/generate/`
    );
    return response.data;
  },

  /**
   * Get extracted data for a document
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object|null>} Extracted data
   */
  getExtractedData: async (projectId, documentId) => {
    try {
      const response = await agenticApiClient.get(
        `/projects/${projectId}/processing/documents/${documentId}/extracted-data/`
      );
      return response.data;
    } catch (error) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  /**
   * Run batch extraction
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Batch extraction results
   */
  runBatch: async (projectId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/batch-extract/`,
      {}
    );
    return response.data;
  },

  /**
   * Get report summary
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Report summary
   */
  getReportSummary: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/report/summary/`
    );
    return response.data;
  },

  /**
   * Get field report
   * @param {string} projectId - Project ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Field report
   */
  getFieldReport: async (projectId, fieldPath) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/report/field/${encodeURIComponent(fieldPath)}/`
    );
    return response.data;
  },

  /**
   * Get project accuracy
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Accuracy overview
   */
  getProjectAccuracy: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/accuracy/overview/`
    );
    return response.data;
  },

  /**
   * Get document comparison
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Document comparison
   */
  getDocumentComparison: async (projectId, documentId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/documents/${documentId}/comparison/`
    );
    return response.data;
  },

  /**
   * Get prompt history
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} Prompt history
   */
  getPromptHistory: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/`
    );
    return response.data;
  },

  /**
   * Tune prompt
   * @param {string} projectId - Project ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Tune result
   */
  tunePrompt: async (projectId, fieldPath) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/prompts/tune/`,
      {
        field_path: fieldPath,
      }
    );
    return response.data;
  },

  /**
   * Promote extracted data to verified data
   * @param {string} projectId - Project ID
   * @param {string} documentId - Document ID
   * @return {Promise<Object>} Promoted verified data
   */
  promoteToVerified: async (projectId, documentId) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/extract/verified/${documentId}/promote/`
    );
    return response.data;
  },
};
