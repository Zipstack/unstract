import axios from "axios";
import Cookies from "js-cookie";
import { useNavigate } from "react-router-dom";

import { getSessionData } from "../helpers/GetSessionData";
import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useSessionStore } from "../store/session-store";
import { useUserSession } from "./useUserSession.js";
import { listFlags } from "../helpers/FeatureFlagsData.js";
import { useAlertStore } from "../store/alert-store";
import useLogout from "./useLogout.js";

let getTrialDetails;
let isPlatformAdmin;
try {
  getTrialDetails = require("../plugins/subscription/trial-helper/fetchTrialDetails.jsx");
  isPlatformAdmin =
    require("../plugins/hooks/usePlatformAdmin.js").usePlatformAdmin();
} catch (err) {
  // Plugin not available
}

// Import useGoogleTagManager hook
let hsSignupEvent;
try {
  hsSignupEvent =
    require("../plugins/hooks/useGoogleTagManager.js").useGoogleTagManager();
} catch {
  // Ignore if hook not available
}

function useSessionValid() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const navigate = useNavigate();
  const userSession = useUserSession();
  const logout = useLogout();

  return async () => {
    try {
      const timestamp = new Date().getTime();
      const userSessionData = await userSession();

      // Return if the user is not authenticated
      if (!userSessionData) {
        return;
      }

      const signedInOrgId = userSessionData?.organization_id;

      // API to get the list of organizations
      const requestOptions = {
        method: "GET",
        url: `/api/v1/organization?q=${timestamp}`,
      };
      const getOrgsRes = await axios(requestOptions);
      const orgs = getOrgsRes?.data?.organizations;
      if (!orgs?.length) {
        throw Error("Organizations not available.");
      }
      if (orgs?.length > 1 && !signedInOrgId?.length) {
        navigate("/setOrg", { state: orgs });
        return;
      }
      let userAndOrgDetails = null;
      const orgId = signedInOrgId || orgs[0].id;
      const csrfToken = Cookies.get("csrftoken");

      if (!orgId || !csrfToken) {
        throw Error("Required fields are missing.");
      }

      // API to set the organization and get the user details
      requestOptions["method"] = "POST";
      requestOptions[
        "url"
      ] = `/api/v1/organization/${orgId}/set?q=${timestamp}`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const setOrgRes = await axios(requestOptions).catch((error) => {
        if (error?.response && error?.response?.status === 403) {
          navigate("/", { state: null });
          window.location.reload();
        }
      });

      const isNewOrg = setOrgRes?.data?.is_new_org || false;
      if (isNewOrg && hsSignupEvent) {
        hsSignupEvent();
      }

      userAndOrgDetails = setOrgRes?.data?.user;
      userAndOrgDetails["orgName"] = setOrgRes?.data?.organization?.name;
      userAndOrgDetails["orgId"] = orgId;
      userAndOrgDetails["csrfToken"] = csrfToken;
      userAndOrgDetails["logEventsId"] = setOrgRes?.data?.log_events_id;

      requestOptions["method"] = "GET";

      requestOptions[
        "url"
      ] = `/api/v1/unstract/${orgId}/users/profile/?q=${timestamp}`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const getUserInfo = await axios(requestOptions);
      userAndOrgDetails["isAdmin"] = getUserInfo?.data?.user?.is_admin;
      userAndOrgDetails["loginOnboardingMessage"] =
        getUserInfo?.data?.user?.login_onboarding_message_displayed;
      userAndOrgDetails["promptOnboardingMessage"] =
        getUserInfo?.data?.user?.prompt_onboarding_message_displayed;

      const zCode = ("; " + document.cookie)
        .split(`; z_code=`)
        .pop()
        .split(";")[0];
      userAndOrgDetails["zCode"] = zCode;

      requestOptions["method"] = "GET";

      requestOptions[
        "url"
      ] = `/api/v1/unstract/${orgId}/adapter/?q=${timestamp}`;
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

      const flags = await listFlags(orgId, csrfToken);
      userAndOrgDetails["flags"] = flags;

      userAndOrgDetails["allOrganization"] = orgs;
      if (isPlatformAdmin) {
        userAndOrgDetails["isPlatformAdmin"] = await isPlatformAdmin();
      }
      userAndOrgDetails["role"] = userSessionData.role;
      // Set the session details
      setSessionDetails(getSessionData(userAndOrgDetails));
    } catch (err) {
      setAlertDetails(handleException(err));
      if (err.response?.status === 402) {
        handleException(err);
        return;
      }

      if (err.request?.status === 412) {
        const response = JSON.parse(err.request.response);
        const domainName = response.domain;
        const code = response.code;
        window.location.href = `/error?code=${code}&domain=${domainName}`;
        // May be need a logout button there or auto logout
        return;
      }

      logout();
    }
  };
}

export default useSessionValid;
