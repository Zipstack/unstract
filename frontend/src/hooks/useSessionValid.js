import axios from "axios";
import Cookies from "js-cookie";
import { useNavigate } from "react-router-dom";

import { getSessionData } from "../helpers/GetSessionData";
import { useExceptionHandler } from "../hooks/useExceptionHandler.jsx";
import { useSessionStore } from "../store/session-store";
import { useUserSession } from "./useUserSession.js";
import { listFlags } from "../helpers/FeatureFlagsData.js";
import { useAlertStore } from "../store/alert-store";

let isPlatformAdmin;
try {
  isPlatformAdmin =
    require("../plugins/hooks/usePlatformAdmin.js").usePlatformAdmin();
} catch (err) {
  // Plugin not available
}

let selectedProduct;
let selectedProductStore;
let PRODUCT_NAMES = {};
let noPlugin = false;

try {
  selectedProductStore = require("../plugins/store/select-product-store.js");
  PRODUCT_NAMES = require("../plugins/llm-whisperer/helper").PRODUCT_NAMES;
} catch {
  noPlugin = true;
  // Ignore if hook not available
}
function useSessionValid() {
  const setSessionDetails = useSessionStore((state) => state.setSessionDetails);
  const handleException = useExceptionHandler();
  const { setAlertDetails } = useAlertStore();
  const navigate = useNavigate();
  const userSession = useUserSession();

  try {
    if (selectedProductStore?.useSelectedProductStore) {
      selectedProduct = selectedProductStore?.useSelectedProductStore(
        (state) => state?.selectedProduct
      );
    }
  } catch (error) {
    // Do nothing
  }
  const navToSelectProduct = (
    userSessionData,
    selectedProductStore,
    selectedProduct
  ) => {
    if (
      userSessionData &&
      selectedProductStore &&
      !Object.values(PRODUCT_NAMES).includes(selectedProduct)
    ) {
      navigate("/selectProduct");
      return true; // Indicate that navigation has occurred
    }
    return false;
  };
  return async () => {
    let userAndOrgDetails = null;
    try {
      const userSessionData = await userSession();
      // Return if the user is not authenticated
      if (!userSessionData) {
        return;
      }

      const signedInOrgId = userSessionData?.organization_id;
      if (!noPlugin) {
        const shouldNavigate = navToSelectProduct(
          userSessionData,
          selectedProductStore,
          selectedProduct
        );
        if (shouldNavigate) {
          return; // Exit early, don't run the remaining steps
        }
      }

      const isUnstract = !(selectedProduct && selectedProduct !== "unstract");

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
      if (orgs?.length > 1 && !signedInOrgId?.length) {
        navigate("/setOrg", { state: orgs });
        return;
      }
      const orgId = signedInOrgId || orgs[0].id;
      const csrfToken = Cookies.get("csrftoken");

      // API to set the organization and get the user details
      requestOptions["method"] = "POST";
      requestOptions["url"] = `/api/v1/organization/${orgId}/set`;
      requestOptions["headers"] = {
        "X-CSRFToken": csrfToken,
      };
      const setOrgRes = await axios(requestOptions).catch((error) => {
        if (error?.response && error?.response?.status === 403) {
          navigate("/", { state: null });
          window.location.reload();
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
      userAndOrgDetails["loginOnboardingMessage"] =
        getUserInfo?.data?.user?.login_onboarding_message_displayed;
      userAndOrgDetails["promptOnboardingMessage"] =
        getUserInfo?.data?.user?.prompt_onboarding_message_displayed;

      const zCode = ("; " + document.cookie)
        .split(`; z_code=`)
        .pop()
        .split(";")[0];
      userAndOrgDetails["zCode"] = zCode;
      if (isUnstract) {
        requestOptions["method"] = "GET";

        requestOptions["url"] = `/api/v1/unstract/${orgId}/adapter/`;
        requestOptions["headers"] = {
          "X-CSRFToken": csrfToken,
        };
        const getAdapterDetails = await axios(requestOptions);
        const adapterTypes = [
          ...new Set(
            getAdapterDetails?.data?.map((obj) =>
              obj.adapter_type.toLowerCase()
            )
          ),
        ];
        userAndOrgDetails["adapters"] = adapterTypes;
      }

      if (isUnstract) {
        const flags = await listFlags(orgId, csrfToken);
        userAndOrgDetails["flags"] = flags;
      }

      userAndOrgDetails["allOrganization"] = orgs;
      if (isPlatformAdmin) {
        userAndOrgDetails["isPlatformAdmin"] = await isPlatformAdmin();
      }
      userAndOrgDetails["role"] = userSessionData.role;
    } catch (err) {
      // TODO: Throw popup error message
      // REVIEW: Add condition to check for trial period status
      if (err.response?.status === 402) {
        handleException(err);
      }

      if (err.request?.status === 412) {
        const response = JSON.parse(err.request.response);
        const domainName = response.domain;
        const code = response.code;
        window.location.href = `/error?code=${code}&domain=${domainName}`;
        // May be need a logout button there or auto logout
      }
      setAlertDetails(handleException(err));
    } finally {
      // Set the session details
      setSessionDetails(getSessionData(userAndOrgDetails));
    }
  };
}

export default useSessionValid;
