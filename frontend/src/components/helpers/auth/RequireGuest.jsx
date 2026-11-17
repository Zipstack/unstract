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
 *
 * It is asked TWICE, in order: about the stored product, then about one a
 * `?selectedProduct=` names (UN-4626, see the fallback below). Both go to the
 * same closed map, so this file still names no product and an OSS-only build
 * is unchanged.
 */
const externalProductHome = (search) => {
  try {
    const stored = selectedProductStore.externalHomeForSelectedProduct();
    if (stored) {
      return stored;
    }
    // THE STORE ANSWERS FOR THIS BROWSER'S LAST CHOICE, WHICH A VISITOR HANDED
    // HERE HAS NOT MADE YET (UN-4626). The other app sends them to a guest
    // route naming the product in the query -- `/landing?selectedProduct=x` --
    // and that is the only statement of intent they carry: nothing on this
    // path writes the store from it, and a first-time arrival has nothing
    // stored at all. Read it, and a visitor who already has a session here
    // reaches the product they asked for instead of falling through to
    // Document Studio, which is the one outcome every branch below exists to
    // avoid.
    //
    // FALLBACK, not an override, deliberately: a stored external home still
    // wins, so this changes nothing for any visitor the store can already
    // answer for, and only rescues the case that is broken today. A product
    // that lives in THIS app stores as `null` here anyway, so a stored
    // `unstract` does not mask the query.
    //
    // `selectedProduct` is the name the login lane already uses for this
    // parameter, so this reads what is already being sent rather than
    // inventing a second spelling.
    //
    // Safe to honour because the plugin consults a CLOSED map of products
    // this deployment configured: an unrecognised name -- or a URL somebody
    // appends hoping to be redirected to it -- answers `null`. This cannot
    // send anybody anywhere the deployment has not already published.
    const asked = new URLSearchParams(search || "").get("selectedProduct");
    return (
      (asked && selectedProductStore.externalHomeForProduct(asked)) || null
    );
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
  const externalHome = externalProductHome(location.search);

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
