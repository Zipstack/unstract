import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useSessionStore } from "../../../store/session-store.js";

let options = {};

function workflowService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  return {
    getWorkflowList: () => {
      options = {
        url: `${path}/workflow/?is_active=True`,
        method: "GET",
      };
      return axiosPrivate(options);
    },
    getWorkflowEndpointList: (endpointType, connectorType) => {
      options = {
        url: `${path}/workflow/endpoint/?endpoint_type=${endpointType}&connection_type=${connectorType}`,
        method: "GET",
      };
      return axiosPrivate(options);
    },
    getProjectList: (myProjects = false) => {
      const params = myProjects ? { created_by: sessionDetails?.id } : {};
      options = {
        url: `${path}/workflow/`,
        method: "GET",
        params,
      };
      return axiosPrivate(options);
    },
    editProject: (name, description, id) => {
      options = {
        url: id ? `${path}/workflow/${id}/` : `${path}/workflow/`,
        method: id ? "PUT" : "POST",
        headers: {
          "X-CSRFToken": csrfToken,
        },
        data: {
          workflow_name: name,
          description,
          [id ? "modified_by" : "created_by"]: sessionDetails?.id,
        },
      };
      return axiosPrivate(options);
    },
    deleteProject: (id) => {
      options = {
        url: `${path}/workflow/${id}/`,
        method: "DELETE",
        headers: {
          "X-CSRFToken": csrfToken,
        },
      };
      return axiosPrivate(options);
    },
    clearFileMarkers: (id) => {
      options = {
        url: `${path}/workflow/${id}/clear-file-marker/`,
        method: "GET",
        headers: {
          "X-CSRFToken": csrfToken,
        },
      };
      return axiosPrivate(options);
    },
    canUpdate: (id) => {
      options = {
        url: `${path}/workflow/${id}/can-update`,
        method: "GET",
      };
      return axiosPrivate(options);
    },
  };
}

export { workflowService };
