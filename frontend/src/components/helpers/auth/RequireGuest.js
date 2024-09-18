import { Navigate, Outlet, useLocation } from "react-router-dom";

import { publicRoutes, onboardCompleted } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
let selectedProductStore;
let isLlmWhisperer;
try {
  selectedProductStore = require("../../../plugins/llm-whisperer/store/select-product-store.js");
} catch {
  // do nothing
}

const RequireGuest = () => {
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const location = useLocation();
  const pathname = location.pathname;
  try {
    isLlmWhisperer =
      selectedProductStore.useSelectedProductStore(
        (state) => state?.selectedProduct
      ) === "llm-whisperer";
  } catch (error) {
    // Do nothing
  }

  let navigateTo = `/${orgName}/onboard`;
  if (isLlmWhisperer) {
    navigateTo = `/llm-whisperer/${orgName}/playground`;
  } else if (onboardCompleted(adapters)) {
    navigateTo = `/${orgName}/tools`;
  }
  if (
    sessionDetails.role === "unstract_reviewer" ||
    sessionDetails.role === "unstract_supervisor"
  ) {
    navigateTo = `/${orgName}/review`;
  }

  return !sessionDetails?.isLoggedIn && publicRoutes.includes(pathname) ? (
    <Outlet />
  ) : (
    <Navigate to={navigateTo} />
  );
};

export { RequireGuest };
