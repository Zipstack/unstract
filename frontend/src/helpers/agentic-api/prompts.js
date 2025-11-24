import { agenticApiClient } from "./client";

export const promptsApi = {
  /**
   * Generate initial prompt
   * @param {string} projectId - Project ID
   * @param {Object} request - {connector_id?}
   * @return {Promise<Object>} Generation response
   */
  generateInitial: async (projectId, request = {}) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/generate-prompt/`,
      request
    );
    return response.data;
  },

  /**
   * Get prompt generation status
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Generation status
   */
  getGenerationStatus: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/generation-status`
    );
    return response.data;
  },

  /**
   * Generate prompt with dependencies
   * @param {string} projectId - Project ID
   * @param {Object} request - {connector_id?}
   * @return {Promise<Object>} Generation response
   */
  generateWithDependencies: async (projectId, request = {}) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/prompts/generate-with-dependencies/`,
      request
    );
    return response.data;
  },

  /**
   * Get generate with dependencies status
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Generation status
   */
  getGenerateWithDepsStatus: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/generate-with-dependencies/status`
    );
    return response.data;
  },

  /**
   * Get latest prompt
   * @param {string} projectId - Project ID
   * @return {Promise<Object>} Latest prompt
   */
  getLatest: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/latest`
    );
    return response.data;
  },

  /**
   * Get all prompts (alias for list)
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} List of prompts
   */
  getAll: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts`
    );
    return response.data;
  },

  /**
   * List all prompts (same as getAll)
   * @param {string} projectId - Project ID
   * @return {Promise<Array>} List of prompts
   */
  list: async (projectId) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts`
    );
    return response.data;
  },

  /**
   * Get prompt by version
   * @param {string} projectId - Project ID
   * @param {number} version - Prompt version
   * @return {Promise<Object>} Prompt
   */
  getByVersion: async (projectId, version) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/${version}`
    );
    return response.data;
  },

  /**
   * Create a new prompt
   * @param {string} projectId - Project ID
   * @param {Object} request - {prompt_text, short_desc, long_desc, base_version?}
   * @return {Promise<Object>} Created prompt
   */
  create: async (projectId, request) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/prompts/`,
      request
    );
    return response.data;
  },

  /**
   * Generate metadata for prompt
   * @param {string} projectId - Project ID
   * @param {Object} request - {prompt_text, base_version}
   * @return {Promise<Object>} Generated metadata
   */
  generateMetadata: async (projectId, request) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/prompts/generate-metadata`,
      request
    );
    return response.data;
  },

  /**
   * Tune prompt for a specific field
   * @param {string} projectId - Project ID
   * @param {Object} request - {field_path, strategy?, connector_id?}
   * @return {Promise<Object>} Tune response
   */
  tune: async (projectId, request) => {
    const response = await agenticApiClient.post(
      `/projects/${projectId}/prompts/tune/`,
      request
    );
    return response.data;
  },

  /**
   * Get tune status
   * @param {string} projectId - Project ID
   * @param {string} fieldPath - Field path
   * @return {Promise<Object>} Tune status
   */
  getTuneStatus: async (projectId, fieldPath) => {
    const response = await agenticApiClient.get(
      `/projects/${projectId}/prompts/tune-status/`,
      { params: { field_path: fieldPath } }
    );
    return response.data;
  },
};
