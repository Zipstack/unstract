import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import useSessionValid from "../../../hooks/useSessionValid";
import { useSessionStore } from "../../../store/session-store";
import { SocketMessages } from "../socket-messages/SocketMessages";
import { GenericLoader } from "../../generic-loader/GenericLoader";
import { PromptRun } from "../../custom-tools/prompt-card/PromptRun";

let selectedProductStore;
let selectedProduct;
try {
  selectedProductStore = require("../../../plugins/llm-whisperer/store/select-product-store.js");
} catch {
  // Ignore if hook not available
}

function PersistentLogin() {
  const [isLoading, setIsLoading] = useState(true);
  const { sessionDetails } = useSessionStore();
  const checkSessionValidity = useSessionValid();

  try {
    if (selectedProductStore?.useSelectedProductStore) {
      selectedProduct = selectedProductStore?.useSelectedProductStore(
        (state) => state?.selectedProduct
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
