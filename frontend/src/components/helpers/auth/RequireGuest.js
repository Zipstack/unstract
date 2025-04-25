import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  publicRoutes,
  onboardCompleted,
  homePagePath,
} from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
let selectedProductStore;
let isLlmWhisperer;
let isVerticals;
try {
  selectedProductStore = require("../../../plugins/store/select-product-store.js");
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
  try {
    isVerticals =
      selectedProductStore.useSelectedProductStore(
        (state) => state?.selectedProduct
      ) === "verticals";
  } catch (error) {
    // Do nothing
  }

  let navigateTo = `/${orgName}/onboard`;
  if (isLlmWhisperer) {
    navigateTo = `/llm-whisperer/${orgName}/playground`;
  } else if (isVerticals) {
    navigateTo = `/verticals/`;
  } else if (onboardCompleted(adapters)) {
    navigateTo = `/${orgName}/${homePagePath}`;
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
