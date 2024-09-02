import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";

function pipelineService(mrq = false) {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails?.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  const requestHeaders = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  };

  return {
    getApiKeys: (id) => {
      const basePipelineUrl = mrq
        ? `${path}/manual_review/api/keys/`
        : `${path}/api/keys/pipeline/${id}/`;
      const requestOptions = {
        url: basePipelineUrl,
        method: "GET",
      };
      return axiosPrivate(requestOptions);
    },
    createApiKey: (apiId, record) => {
      const basePipelineUrl = mrq
        ? `${path}/manual_review/api/key/`
        : `${path}/api/keys/pipeline/${apiId}/`;
      const requestOptions = {
        method: "POST",
        url: basePipelineUrl,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(requestOptions);
    },
    updateApiKey: (keyId, record) => {
      const basePipelineUrl = mrq
        ? `${path}/manual_review/api/key/${keyId}/`
        : `${path}/api/keys/${keyId}/`;
      const requestOptions = {
        method: mrq ? "PATCH" : "PUT",
        url: basePipelineUrl,
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(requestOptions);
    },
    deleteApiKey: (keyId) => {
      const basePipelineUrl = mrq
        ? `${path}/manual_review/api/key/${keyId}/`
        : `${path}/api/keys/${keyId}/`;
      const requestOptions = {
        method: "DELETE",
        url: basePipelineUrl,
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
    getNotifications: (type, id) => {
      const requestOptions = {
        method: "GET",
        url: `${path}/notifications/${type}/${id}/`,
      };
      return axiosPrivate(requestOptions);
    },
    createNotification: (body) => {
      const requestOptions = {
        method: "POST",
        url: `${path}/notifications/`,
        headers: requestHeaders,
        data: body,
      };
      return axiosPrivate(requestOptions);
    },
    updateNotification: (body, id) => {
      const requestOptions = {
        method: "PUT",
        url: `${path}/notifications/${id}/`,
        headers: requestHeaders,
        data: body,
      };
      return axiosPrivate(requestOptions);
    },
    deleteNotification: (id) => {
      const requestOptions = {
        method: "DELETE",
        url: `${path}/notifications/${id}/`,
        headers: requestHeaders,
      };
      return axiosPrivate(requestOptions);
    },
  };
}

export { pipelineService };
