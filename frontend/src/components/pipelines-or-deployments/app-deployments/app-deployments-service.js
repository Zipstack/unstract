import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useSessionStore } from "../../../store/session-store.js";

let options = {};

function appDeploymentsService() {
  const axiosPrivate = useAxiosPrivate();
  const { sessionDetails } = useSessionStore();
  const path = `/api/v1/unstract/${sessionDetails.orgId.replaceAll('"', "")}`;
  const csrfToken = sessionDetails.csrfToken;

  const requestHeaders = {
    "Content-Type": "application/json",
    "X-CSRFToken": csrfToken,
  };

  return {
    getAppDeploymentsList: () => {
      options = {
        url: `${path}/app/`,
        method: "GET",
      };
      return axiosPrivate(options);
    },
    createAppDeployment: (record) => {
      options = {
        url: `${path}/app/`,
        method: "POST",
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    updateAppDeployment: (record) => {
      options = {
        url: `${path}/app/${record?.id}/`,
        method: "PUT",
        headers: requestHeaders,
        data: record,
      };
      return axiosPrivate(options);
    },
    deleteAppDeployment: (id) => {
      options = {
        url: `${path}/app/${id}/`,
        method: "DELETE",
        headers: requestHeaders,
      };
      return axiosPrivate(options);
    },
  };
}

export { appDeploymentsService };
