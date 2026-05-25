import { useAxiosPrivate } from "../../hooks/useAxiosPrivate";
import { useSessionStore } from "../../store/session-store";

const RESOURCE_PATHS = {
  workflow: "workflow",
  pipeline: "pipeline",
  api_deployment: "api/api",
  adapter_instance: "adapter",
  connector_instance: "connector",
  custom_tool: "prompt-studio",
};

function groupsService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails?.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  const requestHeaders = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  };

  return {
    listGroups: (params = {}) => {
      const search = new URLSearchParams(params).toString();
      const suffix = search ? `?${search}` : "";
      return axiosPrivate({
        method: "GET",
        url: `${path}/groups/${suffix}`,
      });
    },
    getGroup: (id) =>
      axiosPrivate({ method: "GET", url: `${path}/groups/${id}/` }),
    createGroup: (data) =>
      axiosPrivate({
        method: "POST",
        url: `${path}/groups/`,
        headers: requestHeaders,
        data,
      }),
    updateGroup: (id, data) =>
      axiosPrivate({
        method: "PATCH",
        url: `${path}/groups/${id}/`,
        headers: requestHeaders,
        data,
      }),
    deleteGroup: (id) =>
      axiosPrivate({
        method: "DELETE",
        url: `${path}/groups/${id}/`,
        headers: requestHeaders,
      }),
    listGroupMembers: (id) =>
      axiosPrivate({ method: "GET", url: `${path}/groups/${id}/members/` }),
    addGroupMembers: (id, userIds) =>
      axiosPrivate({
        method: "POST",
        url: `${path}/groups/${id}/members/`,
        headers: requestHeaders,
        data: { user_ids: userIds },
      }),
    removeGroupMember: (id, userId) =>
      axiosPrivate({
        method: "DELETE",
        url: `${path}/groups/${id}/members/${userId}/`,
        headers: requestHeaders,
      }),
    listGroupResources: (id) =>
      axiosPrivate({ method: "GET", url: `${path}/groups/${id}/resources/` }),
    getEffectiveMembers: (resourceType, resourceId) => {
      const segment = RESOURCE_PATHS[resourceType];
      if (!segment) {
        return Promise.reject(
          new Error(`Unknown resource type: ${resourceType}`),
        );
      }
      return axiosPrivate({
        method: "GET",
        url: `${path}/${segment}/${resourceId}/effective-members/`,
      });
    },
    getAllOrgUsers: () =>
      axiosPrivate({ method: "GET", url: `${path}/users/` }),
  };
}

export { groupsService };
