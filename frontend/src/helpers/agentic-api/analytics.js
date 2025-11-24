import { agenticApiClient } from "./client";

export const analyticsApi = {
  /**
   * Get analytics summary
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Analytics summary
   */
  getSummary: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/summary/`
    );
    // Backend returns total_docs, total_fields, matched_fields, failed_fields, overall_accuracy
    return response.data;
  },

  /**
   * Get top mismatched fields
   * @param {string} projectId - Project ID
   * @param {number} limit - Number of fields to return (default: 10)
   * @return {Promise<Array>} Top mismatched fields
   */
  getTopMismatchedFields: async (projectId, limit = 10) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/top-mismatches/`,
      { params: { limit } }
    );
    // Django returns {mismatches: [...]} but frontend expects array directly
    const data = response.data;
    if (data && data.mismatches) {
      // Transform Django format to frontend format
      return data.mismatches.map((item) => ({
        field_path: item.field_path,
        accuracy: item.accuracy,
        incorrect: item.mismatch_count,
        common_error: item.most_common_error,
      }));
    }
    return Array.isArray(data) ? data : [];
  },

  /**
   * Get category breakdown
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} Category breakdown
   */
  getCategoryBreakdown: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/category-breakdown/`
    );
    return Array.isArray(response.data) ? response.data : [];
  },

  /**
   * Get error type distribution
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} Error type distribution
   */
  getErrorTypeDistribution: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/error-types/`
    );
    // Django returns {error_types: {type: {count, percentage}}, total_errors}
    // Frontend expects [{error_type, count}]
    const data = response.data;
    if (data && data.error_types) {
      return Object.entries(data.error_types).map(([errorType, info]) => ({
        error_type: errorType,
        count: info.count,
      }));
    }
    return Array.isArray(data) ? data : [];
  },

  /**
   * Get field detail
   * @param {string} projectId - Project ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Field detail
   */
  getFieldDetail: async (projectId, fieldPath) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/field/${encodeURIComponent(fieldPath)}/`
    );
    return response.data;
  },

  /**
   * Get mismatch matrix data
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Matrix data {docs, fields, data}
   */
  getMismatchMatrix: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/analytics/matrix/`
    );
    // Backend returns {documents, fields, matrix}
    const data = response.data;
    if (data && data.documents && data.fields && data.matrix) {
      return {
        docs: data.documents,
        fields: data.fields.map((f) => ({
          path: f.field_path,
          field_path: f.field_path,
        })),
        data: data.matrix,
        // Also include raw data for compatibility
        documents: data.documents,
        matrix: data.matrix,
      };
    }
    return { docs: [], fields: [], data: [], documents: [], matrix: [] };
  },

  /**
   * Populate analytics by comparing all documents
   * @param {string} projectId - Project ID
   * @param {boolean} useLlmClassification - Whether to use LLM for error classification
   * @return {Promise<Object>} Population result
   */
  populateAnalytics: async (projectId, useLlmClassification = false) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/analytics/populate/`,
      { use_llm_classification: useLlmClassification }
    );
    return response.data;
  },
};
