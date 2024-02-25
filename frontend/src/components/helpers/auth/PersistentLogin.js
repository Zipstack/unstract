import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";

import { Logo64 } from "../../../assets";
import useSessionValid from "../../../hooks/useSessionValid";
import { useSessionStore } from "../../../store/session-store";

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
    return (
      <div className="center">
        <Logo64 />
      </div>
    );
  }
  return <Outlet />;
}

export { PersistentLogin };
