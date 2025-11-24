import { agenticApiClient } from "./client";

export const projectsApi = {
  /**
   * List all projects
   * @return {Promise<Array>} List of projects
   */
  list: async () => {
    const response = await agenticApiClient.get("/projects/");
    return response.data;
  },

  /**
   * Get a single project
   * @param {string} id - Project ID
   * @return {Promise<Object>} Project details
   */
  get: async (id) => {
    const response = await agenticApiClient.get(`/projects/${id}/`);
    return response.data;
  },

  /**
   * Create a new project
   * @param {Object} data - Project data {name, description?}
   * @return {Promise<Object>} Created project
   */
  create: async (data) => {
    const response = await agenticApiClient.post("/projects/", data);
    return response.data;
  },

  /**
   * Update a project
   * @param {string} id - Project ID
   * @param {Object} data - Update data {name?, description?}
   * @return {Promise<Object>} Updated project
   */
  update: async (id, data) => {
    const response = await agenticApiClient.patch(`/projects/${id}/`, data);
    return response.data;
  },

  /**
   * Update project settings
   * @param {string} id - Project ID
   * @param {Object} data - Settings {extractor_llm_id?, agent_llm_id?, llmwhisperer_id?, lightweight_llm_id?}
   * @return {Promise<Object>} Updated project
   */
  updateSettings: async (id, data) => {
    const response = await agenticApiClient.patch(
      `/projects/${id}/settings/`,
      data
    );
    return response.data;
  },

  /**
   * Delete a project
   * @param {string} id - Project ID
   * @return {Promise<Object>} Delete confirmation message
   */
  delete: async (id) => {
    const response = await agenticApiClient.delete(`/projects/${id}/`);
    return response.data;
  },
};
