import { useEffect } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  getOrgNameFromPathname,
  homePagePath,
  onboardCompleted,
} from "../../../helpers/GetStaticData";
import { getLlmWhispererPage } from "../../../helpers/llmWhispererPage";
import usePostHogEvents from "../../../hooks/usePostHogEvents";
import { useSessionStore } from "../../../store/session-store";

let ProductFruitsManager;
try {
  const mod = await import(
    "../../../plugins/product-fruits/ProductFruitsManager"
  );
  ProductFruitsManager = mod.ProductFruitsManager;
} catch {
  // The component will remain null of it is not available
}
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

  // The persisted page is one-shot: clear it once the user is logged in and
  // any redirect below has had a chance to consume it.
  useEffect(() => {
    if (isLoggedIn && llmWhispererPage) {
      resetSelectedProductPage?.();
    }
  }, [isLoggedIn, llmWhispererPage]);

  let navigateTo = `/${orgName}/onboard`;
  if (isLlmWhisperer) {
    navigateTo = `/llm-whisperer/${orgName}/${getLlmWhispererPage(
      location?.search,
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
