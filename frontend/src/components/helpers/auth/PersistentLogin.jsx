import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { loadPlugin } from "../../../helpers/pluginLoader.js";
import useSessionValid from "../../../hooks/useSessionValid";
import { useSessionStore } from "../../../store/session-store";
import { PromptRun } from "../../custom-tools/prompt-card/PromptRun";
import { GenericLoader } from "../../generic-loader/GenericLoader";
import { SocketMessages } from "../socket-messages/SocketMessages";

const selectedProductStore = await loadPlugin(
  () => import("../../../plugins/store/select-product-store.js"),
);
let selectedProduct;
let setSelectedProduct;

const { SELECTED_PRODUCT, PRODUCT_NAMES = {} } = await loadPlugin(
  () => import("../../../plugins/helpers/common"),
  {},
);

function PersistentLogin() {
  const [isLoading, setIsLoading] = useState(true);
  const { sessionDetails } = useSessionStore();
  const checkSessionValidity = useSessionValid();
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const selectedProductQueryParam = queryParams.get(SELECTED_PRODUCT);

  try {
    if (selectedProductStore?.useSelectedProductStore) {
      selectedProduct = selectedProductStore?.useSelectedProductStore(
        (state) => state?.selectedProduct,
      );
      setSelectedProduct = selectedProductStore.useSelectedProductStore(
        (state) => state?.setSelectedProduct,
      );
    }
  } catch {
    // Plugin hook may throw during initialization
  }

  useEffect(() => {
    let isMounted = true;

    const verifySession = async () => {
      try {
        await checkSessionValidity();
      } finally {
        isMounted && setIsLoading(false);
      }
    };

    if (!sessionDetails?.isLoggedIn) {
      setIsLoading(true); // Only trigger loading if session is invalid
      verifySession();
    } else {
      setIsLoading(false);
    }

    return () => (isMounted = false);
  }, [selectedProduct]);

  useEffect(() => {
    if (
      selectedProductQueryParam &&
      Object.values(PRODUCT_NAMES).includes(selectedProductQueryParam)
    ) {
      // The store and the product constants load independently now.
      setSelectedProduct?.(selectedProductQueryParam);
    }
  }, [selectedProductQueryParam]);

  if (isLoading) {
    return <GenericLoader />;
  }
  return (
    <>
      <Outlet />
      <SocketMessages />
      <PromptRun />
    </>
  );
}

export { PersistentLogin };
