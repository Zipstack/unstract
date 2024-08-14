import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";

import {
  getOrgNameFromPathname,
  onboardCompleted,
} from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
import usePostHogEvents from "../../../hooks/usePostHogEvents";

let ProductFruitsManager;
try {
  ProductFruitsManager =
    require("../../../plugins/product-fruits/ProductFruitsManager").ProductFruitsManager;
} catch {
  // The component will remain null of it is not available
}
let useSelectedProductStore;
let selectedProduct;
try {
  useSelectedProductStore =
    require("../../../plugins/llm-whisperer/store/select-produc-store").useSelectedProductStore;
} catch {
  // do nothing
}

const RequireAuth = () => {
  const { sessionDetails } = useSessionStore();
  const { setPostHogIdentity } = usePostHogEvents();
  const location = useLocation();
  const isLoggedIn = sessionDetails?.isLoggedIn;
  const orgName = sessionDetails?.orgName;
  const pathname = location?.pathname;
  const adapters = sessionDetails?.adapters;
  const currOrgName = getOrgNameFromPathname(pathname);
  if (useSelectedProductStore) {
    selectedProduct = useSelectedProductStore((state) => state.selectedProduct);
  }
  const isLlmWhisperer = selectedProduct && selectedProduct === "llm-whisperer";

  useEffect(() => {
    if (!sessionDetails?.isLoggedIn) {
      return;
    }

    setPostHogIdentity();
  }, [sessionDetails]);

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

  if (!isLoggedIn) {
    return <Navigate to="/landing" state={{ from: location }} replace />;
  }

  if (!isLlmWhisperer && currOrgName !== orgName) {
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
