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
        url: "/api/v1/organization",
      };
      const getOrgsRes = await axios(requestOptions);
      const orgs = getOrgsRes?.data?.organizations;
      if (!orgs?.length) {
        throw Error("Organizations not available.");
      }
      let userAndOrgDetails = null;
      const orgId = orgs[0]?.id;
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
      const setOrgRes = await axios(requestOptions);
      userAndOrgDetails = setOrgRes?.data?.user;
      userAndOrgDetails["orgName"] = setOrgRes?.data?.organization?.name;
      userAndOrgDetails["orgId"] = orgId;
      userAndOrgDetails["csrfToken"] = csrfToken;

      requestOptions["method"] = "GET";

      requestOptions["url"] = `/api/v1/unstract/${orgId}/users/profile/`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const getUserInfo = await axios(requestOptions);
      userAndOrgDetails["isAdmin"] = getUserInfo?.data?.user?.is_admin;

      const zCode = ("; " + document.cookie)
        .split(`; z_code=`)
        .pop()
        .split(";")[0];
      userAndOrgDetails["zCode"] = zCode;

      requestOptions["method"] = "GET";

      requestOptions["url"] = `/api/v1/unstract/${orgId}/adapter/`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const getAdapterDetails = await axios(requestOptions);
      const adapterTypes = [
        ...new Set(
          getAdapterDetails?.data?.map((obj) => obj.adapter_type.toLowerCase())
        ),
      ];
      userAndOrgDetails["adapters"] = adapterTypes;

      // Set the session details
      setSessionDetails(getSessionData(userAndOrgDetails));
    } catch (err) {
      // TODO: Throw popup error message

      if (err.request.status === 412) {
        const domainName = JSON.parse(err.request.response).domain;
        window.location.href = `/error?code=USF&domain=${domainName}`;
        // May be need a logout button there or auto logout
      }
    }
  };
}

export default useSessionValid;
