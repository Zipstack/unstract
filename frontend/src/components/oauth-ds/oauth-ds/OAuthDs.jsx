import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { O_AUTH_PROVIDERS, getBaseUrl } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import GoogleOAuthButton from "../google/GoogleOAuthButton.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
function OAuthDs({
  oAuthProvider,
  setCacheKey,
  setStatus,
  selectedSourceId,
  workflowId,
  connectorType,
}) {
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  // Create workflow and connector-type specific OAuth storage keys
  const oauthCacheKey = `oauth-cachekey-${workflowId}-${connectorType}-${selectedSourceId}`;
  const oauthStatusKey = `oauth-status-${workflowId}-${connectorType}-${selectedSourceId}`;

  const [oauthStatus, setOAuthStatus] = useState(() => {
    // Initialize from workflow and connector-type specific status to prevent contamination
    return localStorage.getItem(oauthStatusKey);
  });

  useEffect(() => {
    const handleStorageChange = () => {
      // Listen for changes to our specific workflow-connector combination only
      const updatedOAuthStatus = localStorage.getItem(oauthStatusKey);
      if (updatedOAuthStatus) {
        setOAuthStatus(updatedOAuthStatus);
        setStatus(updatedOAuthStatus);
      }
    };

    window.addEventListener("storage", handleStorageChange);

    // Load persisted cache key if available
    const persistedCacheKey = localStorage.getItem(oauthCacheKey);
    if (persistedCacheKey) {
      setCacheKey(persistedCacheKey);
    }

    // Set initial status from workflow and connector-type specific status only
    const workflowSpecificStatus = localStorage.getItem(oauthStatusKey);
    if (workflowSpecificStatus) {
      setStatus(workflowSpecificStatus);
      setOAuthStatus(workflowSpecificStatus);
    }

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      // Don't clear localStorage on unmount to persist across tab switches
    };
  }, [
    selectedSourceId,
    workflowId,
    connectorType,
    oauthCacheKey,
    oauthStatusKey,
    setCacheKey,
    setStatus,
  ]);

  const handleOAuth = async () => {
    try {
      // Store workflow and connector context in sessionStorage for OAuth callback (survives window.open)
      const oauthConnectorContext = `${workflowId}-${connectorType}-${selectedSourceId}`;
      sessionStorage.setItem("oauth-current-connector", oauthConnectorContext);

      const requestOptions = {
        method: "GET",
        url: `/api/v1/oauth/cache-key/${oAuthProvider}`,
      };

      const response = await axiosPrivate(requestOptions);
      const cacheKey = response?.data?.cache_key;
      const encodedCacheKey = encodeURIComponent(cacheKey);
      setCacheKey(cacheKey);

      // Persist cache key to localStorage
      localStorage.setItem(oauthCacheKey, cacheKey);

      const baseUrl = getBaseUrl();

      const url = `${baseUrl}/api/v1/oauth/login/${oAuthProvider}?oauth-key=${encodedCacheKey}`;

      // Open in a new window
      window.open(
        url,
        "_blank",
        "toolbar=yes,scrollbars=yes,resizable=yes,top=200,left=500,width=500,height=600"
      );
    } catch (err) {
      setAlertDetails(handleException(err));
    }
  };

  if (O_AUTH_PROVIDERS["GOOGLE"] === oAuthProvider) {
    return (
      <>
        <GoogleOAuthButton handleOAuth={handleOAuth} status={oauthStatus} />
      </>
    );
  }

  return <Typography>Provider not available.</Typography>;
}

OAuthDs.propTypes = {
  oAuthProvider: PropTypes.string,
  setCacheKey: PropTypes.func,
  setStatus: PropTypes.func,
  selectedSourceId: PropTypes.string.isRequired,
  workflowId: PropTypes.string.isRequired,
  connectorType: PropTypes.string.isRequired,
};

export { OAuthDs };
