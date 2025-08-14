import { Typography } from "antd";
import PropTypes from "prop-types";
import { useEffect, useState } from "react";

import { O_AUTH_PROVIDERS, getBaseUrl } from "../../../helpers/GetStaticData";
import { useAxiosPrivate } from "../../../hooks/useAxiosPrivate.js";
import { useAlertStore } from "../../../store/alert-store";
import GoogleOAuthButton from "../google/GoogleOAuthButton.jsx";
import { useExceptionHandler } from "../../../hooks/useExceptionHandler.jsx";
function OAuthDs({ oAuthProvider, setCacheKey, setStatus, selectedSourceId }) {
  const axiosPrivate = useAxiosPrivate();
  const { setAlertDetails } = useAlertStore();
  const handleException = useExceptionHandler();

  const oauthCacheKey = `oauth-cachekey-${selectedSourceId}`;

  const [oauthStatus, setOAuthStatus] = useState(() => {
    // Initialize from connector-specific status only to prevent contamination
    return localStorage.getItem(`oauth-status-${selectedSourceId}`);
  });

  useEffect(() => {
    const connectorStatusKey = `oauth-status-${selectedSourceId}`;

    const handleStorageChange = () => {
      // Listen for changes to our specific connector's status only
      const updatedOAuthStatus = localStorage.getItem(connectorStatusKey);
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

    // Set initial status from connector-specific status only
    const connectorSpecificStatus = localStorage.getItem(connectorStatusKey);
    if (connectorSpecificStatus) {
      setStatus(connectorSpecificStatus);
      setOAuthStatus(connectorSpecificStatus);
    }

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      // Don't clear localStorage on unmount to persist across tab switches
    };
  }, [selectedSourceId]);

  const handleOAuth = async () => {
    try {
      // Store connector ID in sessionStorage for OAuth callback (survives window.open)
      sessionStorage.setItem("oauth-current-connector", selectedSourceId);

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
};

export { OAuthDs };
