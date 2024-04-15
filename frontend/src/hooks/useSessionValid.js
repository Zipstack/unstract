import axios from "axios";

import { getSessionData } from "../helpers/GetSessionData";
import { getCookie } from "../helpers/GetCookie.js";
import { userSession } from "../helpers/GetUserSession.js";
import { useSessionStore } from "../store/session-store";
import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useNavigate } from "react-router-dom";

let getTrialDetails;
try {
  getTrialDetails = require("../plugins/subscription/trial-helper/fetchTrialDetails.jsx");
} catch (err) {
  // Plugin not available
}

function useSessionValid() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const handleException = useExceptionHandler();
  const navigate = useNavigate();
  return async () => {
    try {
      const userSessionData = await userSession();
      const signedInOrgId = userSessionData?.organization_id;

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
      if (orgs?.length > 1 && signedInOrgId && signedInOrgId === "public") {
        navigate("/setOrg", { state: orgs });
        return;
      }
      let userAndOrgDetails = null;
      const orgId = signedInOrgId || orgs[0].id;
      const csrfToken = getCookie("csrftoken");

      // API to set the organization and get the user details
      requestOptions["method"] = "POST";
      requestOptions["url"] = `/api/v1/organization/${orgId}/set`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const setOrgRes = await axios(requestOptions).catch((error) => {
        if (error?.response && error?.response?.status === 403) {
          navigate("/", { state: null });
        }
      });
      userAndOrgDetails = setOrgRes?.data?.user;
      userAndOrgDetails["orgName"] = setOrgRes?.data?.organization?.name;
      userAndOrgDetails["orgId"] = orgId;
      userAndOrgDetails["csrfToken"] = csrfToken;
      userAndOrgDetails["logEventsId"] = setOrgRes?.data?.log_events_id;

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

      if (getTrialDetails) {
        const remainingTrialDays = await getTrialDetails.fetchTrialDetails(
          orgId,
          csrfToken
        );
        if (remainingTrialDays)
          userAndOrgDetails["remainingTrialDays"] = remainingTrialDays;
      }
      userAndOrgDetails["allOrganization"] = orgs;

      // Set the session details
      setSessionDetails(getSessionData(userAndOrgDetails));
    } catch (err) {
      // TODO: Throw popup error message
      if (err.response?.status === 402) {
        handleException(err);
      }

      if (err.request?.status === 412) {
        const domainName = JSON.parse(err.request.response).domain;
        window.location.href = `/error?code=USF&domain=${domainName}`;
        // May be need a logout button there or auto logout
      }
    }
  };
}

export default useSessionValid;
