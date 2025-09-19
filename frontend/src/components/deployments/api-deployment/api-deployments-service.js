import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useSessionStore } from "../../../store/session-store.js";

let options = {};

function apiDeploymentsService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  const requestHeaders = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  };

  return {
    getApiDeploymentsList: () => {
      options = {
        url: `${path}/api/deployment/`,
        method: "GET",
      };
      return axiosPrivate(options);
    },
    createApiDeployment: (record) => {
      options = {
        url: `${path}/api/deployment/`,
        method: "POST",
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    updateApiDeployment: (record) => {
      options = {
        url: `${path}/api/deployment/${record?.id}/`,
        method: "PUT",
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    deleteApiDeployment: (id) => {
      options = {
        url: `${path}/api/deployment/${id}/`,
        method: "DELETE",
        headers: requestHeaders,
      };
      return axiosPrivate(options);
    },
    getApiKeys: (id) => {
      options = {
        method: "GET",
        url: `${path}/api/keys/api/${id}/`,
      };
      return axiosPrivate(options);
    },
    createApiKey: (apiId, record) => {
      options = {
        method: "POST",
        url: `${path}/api/keys/api/${apiId}/`,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    updateApiKey: (keyId, record) => {
      options = {
        method: "PUT",
        url: `${path}/api/keys/${keyId}/`,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    deleteApiKey: (keyId) => {
      options = {
        method: "DELETE",
        url: `${path}/api/keys/${keyId}/`,
        headers: requestHeaders,
      };
      return axiosPrivate(options);
    },
    downloadPostmanCollection: (id) => {
      options = {
        method: "GET",
        url: `${path}/api/postman_collection/${id}/`,
        responseType: "blob",
      };
      return axiosPrivate(options);
    },
    getDeploymentsByWorkflowId: (workflowId) => {
      options = {
        method: "GET",
        url: `${path}/api/deployment/?workflow=${workflowId}`,
      };
      return axiosPrivate(options);
    },
    getSharedUsers: (id) => {
      options = {
        method: "GET",
        url: `${path}/api/deployment/${id}/users/`,
      };
      return axiosPrivate(options);
    },
    updateSharing: (id, sharedUsers, shareWithEveryone) => {
      options = {
        method: "PATCH",
        url: `${path}/api/deployment/${id}/`,
        headers: requestHeaders,
        data: {
          shared_users: sharedUsers,
          shared_to_org: shareWithEveryone,
        },
      };
      return axiosPrivate(options);
    },
    getAllUsers: () => {
      options = {
        method: "GET",
        url: `${path}/users/`,
      };
      return axiosPrivate(options);
    },
  };
}

export { apiDeploymentsService };
