import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  homePagePath,
  onboardCompleted,
  publicRoutes,
} from "../../../helpers/GetStaticData";
import { getLlmWhispererPage } from "../../../helpers/llmWhispererPage";
import { useSessionStore } from "../../../store/session-store";

let selectedProductStore;
let isLlmWhisperer;
let isVerticals;
try {
  selectedProductStore = await import(
    "../../../plugins/store/select-product-store.js"
  );
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
  let llmWhispererPage;
  let resetSelectedProductPage;
  try {
    llmWhispererPage = selectedProductStore.useSelectedProductStore(
      (state) => state?.selectedProductPage,
    );
    resetSelectedProductPage = selectedProductStore.useSelectedProductStore(
      (state) => state?.resetSelectedProductPage,
    );
  } catch (_error) {
    // Do nothing
  }

  // The persisted page is one-shot: clear it once the user is logged in and
  // the redirect below has consumed it.
  useEffect(() => {
    if (sessionDetails?.isLoggedIn && llmWhispererPage) {
      resetSelectedProductPage?.();
    }
  }, [sessionDetails?.isLoggedIn, llmWhispererPage]);

  let navigateTo = `/${orgName}/onboard`;
  if (isLlmWhisperer) {
    navigateTo = `/llm-whisperer/${orgName}/${getLlmWhispererPage(
      location.search,
      llmWhispererPage,
    )}`;
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
