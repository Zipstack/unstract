import { Navigate, Outlet, useLocation } from "react-router-dom";

import { publicRoutes, onboardCompleted } from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
let useSelectedProductStore;
let selectedProduct;
try {
  useSelectedProductStore =
    require("../../../plugins/llm-whisperer/store/select-produc-store").useSelectedProductStore;
} catch {
  // do nothing
}

const RequireGuest = () => {
  const { sessionDetails } = useSessionStore();
  const { orgName, adapters } = sessionDetails;
  const location = useLocation();
  const pathname = location.pathname;
  try {
    if (useSelectedProductStore) {
      selectedProduct = useSelectedProductStore(
        (state) => state?.selectedProduct
      );
    }
  } catch (error) {
    // Do nothing
  }
  const isLlmWhisperer = selectedProduct && selectedProduct === "llm-whisperer";

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
