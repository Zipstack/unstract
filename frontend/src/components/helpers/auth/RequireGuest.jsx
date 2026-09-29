import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  homePagePath,
  onboardCompleted,
  publicRoutes,
} from "../../../helpers/GetStaticData";
import { loadPlugin } from "../../../helpers/pluginLoader.js";
import { useSessionStore } from "../../../store/session-store";

const selectedProductStore = await loadPlugin(
  () => import("../../../plugins/store/select-product-store.js"),
);
let isLlmWhisperer;
let isVerticals;

const RequireGuest = () => {
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const location = useLocation();
  const pathname = location.pathname;
  try {
    isLlmWhisperer =
      selectedProductStore.useSelectedProductStore(
        (state) => state?.selectedProduct,
      ) === "llm-whisperer";
  } catch (_error) {
    // Do nothing
  }
  try {
    isVerticals =
      selectedProductStore.useSelectedProductStore(
        (state) => state?.selectedProduct,
      ) === "verticals";
  } catch (_error) {
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
