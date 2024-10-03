import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import useSessionValid from "../../../hooks/useSessionValid";
import { useSessionStore } from "../../../store/session-store";
import { SocketMessages } from "../socket-messages/SocketMessages";
import { GenericLoader } from "../../generic-loader/GenericLoader";
import { PromptRun } from "../../custom-tools/prompt-card/PromptRun";

function PersistentLogin() {
  const [isLoading, setIsLoading] = useState(true);
  const { sessionDetails } = useSessionStore();
  const checkSessionValidity = useSessionValid();

  useEffect(() => {
    let isMounted = true;

    const verifySession = async () => {
      try {
        await checkSessionValidity();
      } finally {
        isMounted && setIsLoading(false);
      }
    };

    !sessionDetails?.isLoggedIn ? verifySession() : setIsLoading(false);

    return () => (isMounted = false);
  }, []);

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
