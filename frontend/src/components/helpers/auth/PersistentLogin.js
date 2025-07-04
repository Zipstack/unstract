import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";

import useSessionValid from "../../../hooks/useSessionValid";
import { useSessionStore } from "../../../store/session-store";
import { SocketMessages } from "../socket-messages/SocketMessages";
import { GenericLoader } from "../../generic-loader/GenericLoader";
import { PromptRun } from "../../custom-tools/prompt-card/PromptRun";

let selectedProductStore;
let selectedProduct;
let setSelectedProduct;
let SELECTED_PRODUCT;
let PRODUCT_NAMES = {};
try {
  selectedProductStore = require("../../../plugins/store/select-product-store.js");
  SELECTED_PRODUCT =
    require("../../../plugins/helpers/common").SELECTED_PRODUCT;
  PRODUCT_NAMES = require("../../../plugins/helpers/common").PRODUCT_NAMES;
} catch {
  // Ignore if hook not available
}

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
        (state) => state?.selectedProduct
      );
      setSelectedProduct = selectedProductStore.useSelectedProductStore(
        (state) => state?.setSelectedProduct
      );
    }
  } catch (error) {
    // Do nothing
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
      setSelectedProduct(selectedProductQueryParam);
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
