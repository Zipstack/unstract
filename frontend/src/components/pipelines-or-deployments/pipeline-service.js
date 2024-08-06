import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";

function pipelineService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  const requestHeaders = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  };

  return {
    getApiKeys: (id) => {
      const requestOptions = {
        url: `${path}/api/keys/pipeline/${id}/`,
        method: "GET",
      };
      return axiosPrivate(requestOptions);
    },
    createApiKey: (apiId, record) => {
      const requestOptions = {
        method: "POST",
        url: `${path}/api/keys/pipeline/${apiId}/`,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(requestOptions);
    },
    updateApiKey: (keyId, record) => {
      const requestOptions = {
        method: "PUT",
        url: `${path}/api/keys/${keyId}/`,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(requestOptions);
    },
    deleteApiKey: (keyId) => {
      const requestOptions = {
        method: "DELETE",
        url: `${path}/api/keys/${keyId}/`,
        headers: requestHeaders,
      };
      return axiosPrivate(requestOptions);
    },
    downloadPostmanCollection: (id) => {
      const requestOptions = {
        method: "GET",
        url: `${path}/pipeline/api/postman_collection/${id}/`,
        responseType: "blob",
      };
      return axiosPrivate(requestOptions);
    },
    getNotifications: () => {
      const requestOptions = {
        method: "GET",
        url: `${path}/notifications/`,
      };
      return axiosPrivate(requestOptions);
    },
  };
}

export { pipelineService };
