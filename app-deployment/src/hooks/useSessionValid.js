import axios from "axios";

import { getSessionData } from "../helpers/GetSessionData";
import { useSessionStore } from "../store/session-store";

function useSessionValid() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  return async () => {
    try {
      // API to get the list of organizations
      const requestOptions = {
        method: "GET",
        url: "/api/v1/apps/load/",
      };
      const getAppDetails = await axios(requestOptions);
      let userAndOrgDetails = null;
      const orgId = getAppDetails.data.org_id;
      const appId = getAppDetails.data.app_id;
      const csrfToken = ("; " + document.cookie)
        .split(`; csrftoken=`)
        .pop()
        .split(";")[0];

      // API to set the organization and get the user details
      requestOptions["method"] = "POST";
      requestOptions["url"] = `/api/v1/organization/${orgId}/set`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      requestOptions["data"] = {
        app_id: appId,
      };
      const setOrgRes = await axios(requestOptions);
      userAndOrgDetails = setOrgRes?.data?.user;
      userAndOrgDetails["orgName"] = setOrgRes?.data?.organization?.name;
      userAndOrgDetails["orgId"] = orgId;
      userAndOrgDetails["appId"] = appId;
      userAndOrgDetails["csrfToken"] = csrfToken;

      requestOptions["method"] = "GET";

      requestOptions["url"] = `/api/v1/unstract/${orgId}/users/`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const getAllUsers = await axios(requestOptions);
      const getLoggedInUser = getAllUsers.data.members.find(
        (user) => user.email === setOrgRes?.data?.user.email
      );
      const isAdmin = getLoggedInUser.role === "unstract_admin";
      userAndOrgDetails["isAdmin"] = isAdmin;

      const zCode = ("; " + document.cookie)
        .split(`; z_code=`)
        .pop()
        .split(";")[0];
      userAndOrgDetails["zCode"] = zCode;
      setSessionDetails(getSessionData(userAndOrgDetails));
    } catch (err) {
      if (err.request.status === 401) {
        window.location.href =
          "/api/v1/login?redirect_url=" + window.location.href;
      }
      if (err.request.status === 403) {
        window.location.href =
          "/error?status=403&title=403&subTitle=Not authorized";
        // May be need a logout button there or auto logout
      }
      if (err.request.status === 404) {
        window.location.href =
          "/error?status=404&title=404&subTitle=Sorry, the page you visited does not exist.";
        // May be need a logout button there or auto logout
      }
    }
  };
}

export default useSessionValid;
