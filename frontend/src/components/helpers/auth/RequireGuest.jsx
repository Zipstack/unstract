import { Navigate, Outlet, useLocation } from "react-router-dom";

import {
  homePagePath,
  onboardCompleted,
  publicRoutes,
} from "../../../helpers/GetStaticData";
import { useSessionStore } from "../../../store/session-store";
import { ExternalRedirect } from "./ExternalRedirect";

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

/*
 * A product whose home is not a route in this app.
 *
 * Every destination below resolves to a path this SPA serves, which is
 * fine while every product IS one of this SPA's. A deployment can pair
 * this app with a separate one, though — `config.flowUrl` is the existing
 * example — and a visitor whose chosen product is that separate app has no
 * address here. Without this they fall through to the last branch and land
 * on Document Studio, which is not what they chose.
 *
 * The plugin store answers, because the set of products and where each one
 * lives is its knowledge, not this file's. Absent plugin, absent hook or
 * absent answer all mean "this product is one of ours", which is the
 * behaviour this file had before the hook existed and is what an OSS-only
 * build gets.
 */
const externalProductHome = () => {
  try {
    return selectedProductStore.externalHomeForSelectedProduct() || null;
  } catch {
    return null;
  }
};

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

  // Checked before the in-app destinations below: a separate app's home is
  // not one of them, so none of those branches can express it.
  const externalHome = externalProductHome();

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

  if (!sessionDetails?.isLoggedIn && publicRoutes.includes(pathname)) {
    return <Outlet />;
  }
  // `<Navigate>` cannot leave this app — it would ask the router for a
  // path that is not registered here — so a separate app's home needs a
  // real navigation.
  if (externalHome) {
    return <ExternalRedirect to={externalHome} />;
  }
  return <Navigate to={navigateTo} />;
};

export { RequireGuest };
