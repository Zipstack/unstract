import { agenticApiClient } from "./client";

export const schemaApi = {
  /**
   * Get project schema
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Schema
   */
  get: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/schema/`
    );
    return response.data;
  },

  /**
   * Update project schema
   * @param {string} projectId - Project ID
   * @param {Object} jsonSchema - Schema object
   * @return {Promise<Object>} Updated schema
   */
  update: async (projectId, jsonSchema) => {
    const response = await agenticApiClient.put(
      `/projects/${projectId}/schema/`,
      jsonSchema
    );
    return response.data;
  },

  /**
   * Generate schema
   * @param {string} projectId - Project ID
   * @param {Object} request - {connector_id?}
   * @return {Promise<Object>} Generation response
   */
  generate: async (projectId, request = {}) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/schema/generate/`,
      request
    );
    return response.data;
  },

  /**
   * Get schema generation status
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Generation status
   */
  getGenerationStatus: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/schema/generation-status/`
    );
    return response.data;
  },

  /**
   * Generate schema lazily (with dependencies)
   * @param {string} projectId - Project ID
   * @param {Object} request - {connector_id?}
   * @return {Promise<Object>} Generation response
   */
  generateLazy: async (projectId, request = {}) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/schema/generate-lazy/`,
      request
    );
    return response.data;
  },

  /**
   * Get lazy schema generation status
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Generation status
   */
  getLazyGenerationStatus: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/schema/lazy-generation-status/`
    );
    return response.data;
  },
};
