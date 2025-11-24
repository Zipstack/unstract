import axios from "axios";

import { agenticApiClient } from "./client";

export const connectorsApi = {
  /**
   * List all connectors from the system adapter API
   * @param {string} orgId - Organization ID
   * @return {Promise<Array>} List of connectors
   */
  list: async (orgId) => {
    // Use the existing adapter API endpoint instead of agentic-specific one
    const response = await axios.get(`/api/v1/unstract/${orgId}/adapter/`);
    return response.data;
  },

  /**
   * Get a single connector
   * @param {string} id - Connector ID
   * @return {Promise<Object>} Connector details
   */
  get: async (id) => {
    const response = await agenticApiClient.get(`/connectors/${id}`);
    return response.data;
  },

  /**
   * Create a new connector
   * @param {Object} data - Connector data {type, provider, name, model, credentials, params?}
   * @return {Promise<Object>} Created connector
   */
  create: async (data) => {
    const response = await agenticApiClient.post("/connectors", data);
    return response.data;
  },

  /**
   * Update a connector
   * @param {string} id - Connector ID
   * @param {Object} data - Update data
   * @return {Promise<Object>} Updated connector
   */
  update: async (id, data) => {
    const response = await agenticApiClient.patch(`/connectors/${id}`, data);
    return response.data;
  },

  /**
   * Delete a connector
   * @param {string} id - Connector ID
   * @return {Promise<Object>} Delete confirmation
   */
  delete: async (id) => {
    const response = await agenticApiClient.delete(`/connectors/${id}`);
    return response.data;
  },

  /**
   * Test a connector
   * @param {string} id - Connector ID
   * @return {Promise<Object>} Test result
   */
  test: async (id) => {
    const response = await agenticApiClient.post(`/connectors/${id}/test`);
    return response.data;
  },
};
