import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  getOrgNameFromPathname,
  homePagePath,
  onboardCompleted,
} from "../../../helpers/GetStaticData";
import { loadPlugin } from "../../../helpers/pluginLoader.js";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useSessionStore } from "../../../store/session-store";

const ProductFruitsManager = await loadPlugin(() =>
  import("../../../plugins/product-fruits/ProductFruitsManager").then(
    (m) => m.ProductFruitsManager,
  ),
);
const selectedProductStore = await loadPlugin(
  () => import("../../../plugins/store/select-product-store.js"),
);
let isLlmWhisperer;
let isVerticals;

const RequireAuth = () => {
  const { sessionDetails } = useSessionStore();
  const { setPostHogIdentity } = usePostHogEvents();
  const location = useLocation();
  const isLoggedIn = sessionDetails?.isLoggedIn;
  const orgName = sessionDetails?.orgName;
  const pathname = location?.pathname;
  const adapters = sessionDetails?.adapters;
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

  const currOrgName = getOrgNameFromPathname(
    pathname,
    isLlmWhisperer || isVerticals,
  );
  useEffect(() => {
    if (!sessionDetails?.isLoggedIn) {
      return;
    }

    setPostHogIdentity();
  }, [sessionDetails]);

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

  if (!isLoggedIn) {
    return <Navigate to="/landing" state={{ from: location }} replace />;
  }

  if (currOrgName !== orgName) {
    return <Navigate to={navigateTo} />;
  }

  return (
    <>
      {ProductFruitsManager && <ProductFruitsManager />}
      <Outlet />
    </>
  );
};

export { RequireAuth };
